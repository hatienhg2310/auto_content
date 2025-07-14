import asyncio
import aiohttp
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import requests
from typing import List, Optional, Tuple
import os
import uuid
import json
from datetime import datetime
import httpx
import openai

from src.models import GeneratedImages, WorkflowConfig
from src.prompt_manager import prompt_manager
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class ImageGenerator:
    """
    Dịch vụ tạo ảnh sử dụng các AI image generation APIs với tích hợp system prompts
    """
    
    def __init__(self):
        self.config = WorkflowConfig()
        self.storage_path = settings.images_storage_path
        self.prompt_manager = prompt_manager
        # Bỏ qua OpenAI DALL-E, chỉ sử dụng Midjourney
        self.dalle_client = None
        
    async def generate_dalle_image(self, prompt: str, size: str = "1024x1024") -> Optional[str]:
        """
        DALL-E đã được vô hiệu hóa - chỉ sử dụng Midjourney/Piapi
        """
        logger.info("DALL-E đã được vô hiệu hóa, bỏ qua tạo ảnh")
        return None

    async def generate_optimized_image_with_midjourney_prompt(self, title: str, keywords: List[str]) -> Optional[str]:
        """
        Tạo ảnh sử dụng prompts được tối ưu bởi Midjourney system prompt
        """
        try:
            # Sử dụng system prompt để tạo Midjourney-style prompts
            midjourney_prompt = self.prompt_manager.get_midjourney_generation_prompt(title, keywords)
            
            # Bỏ qua OpenAI, chỉ tạo fallback prompts
            logger.info("Bỏ qua OpenAI để tạo image prompts, sử dụng fallback prompts")
            response_text = f"""
            1. cinematic {title.lower()}, professional lighting, 16:9 composition, negative space for text overlay, high quality photography --ar 16:9 --v 7
            2. artistic composition for {title.lower()}, dramatic lighting, negative space for text, high quality --ar 16:9 --v 7  
            3. professional thumbnail style for {title.lower()}, engaging visual, text overlay space, modern design --ar 16:9 --v 7
            """
            
            # Parse prompts từ response
            import re
            code_blocks = re.findall(r'```(.*?)```', response_text, re.DOTALL)
            
            optimized_prompt = ""
            if code_blocks:
                # Lấy prompt đầu tiên
                optimized_prompt = code_blocks[0].strip()
            else:
                # Fallback: lấy dòng đầu tiên có độ dài phù hợp
                lines = response_text.split('\n')
                for line in lines:
                    if len(line.strip()) > 50:  # Prompts thường dài
                        optimized_prompt = line.strip()
                        break
            
            if not optimized_prompt:
                optimized_prompt = f"cinematic scene related to {title}, professional lighting, shallow depth of field, 16:9 aspect ratio --ar 16:9 --v 7"
            
            # Làm sạch prompt cho DALL-E (loại bỏ Midjourney-specific parameters)
            dalle_prompt = self._clean_prompt_for_dalle(optimized_prompt)
            
            logger.info(f"Optimized prompt: {dalle_prompt[:100]}...")
            
            # Tạo ảnh với DALL-E sử dụng prompt đã tối ưu
            return await self.generate_dalle_image(dalle_prompt, "1792x1024")  # 16:9 aspect ratio
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo ảnh với Midjourney prompt: {str(e)}")
            # Bỏ qua DALL-E fallback
            return None

    def _clean_prompt_for_dalle(self, midjourney_prompt: str) -> str:
        """
        Làm sạch Midjourney prompt để phù hợp với DALL-E
        """
        # Loại bỏ Midjourney-specific parameters
        dalle_prompt = midjourney_prompt
        
        # Loại bỏ các tham số Midjourney
        midjourney_params = ['--ar', '--v', '--style', '--quality', '--chaos', '--seed', '--stop', '--repeat']
        for param in midjourney_params:
            if param in dalle_prompt:
                # Tìm và loại bỏ parameter và giá trị của nó
                parts = dalle_prompt.split(param)
                if len(parts) > 1:
                    # Lấy phần trước parameter
                    dalle_prompt = parts[0].strip()
                    # Nếu có nhiều parts, có thể ghép phần sau (loại bỏ giá trị parameter)
                    if len(parts) > 2:
                        remaining = ' '.join(parts[2:])
                        dalle_prompt += ' ' + remaining
        
        # Thêm mô tả cho DALL-E
        dalle_prompt += ", digital art, high quality, detailed"
        
        # Giới hạn độ dài prompt cho DALL-E
        if len(dalle_prompt) > 1000:
            dalle_prompt = dalle_prompt[:1000]
        
        return dalle_prompt.strip()

    async def _generate_via_replicate(self, prompt: str) -> Optional[str]:
        """
        Tạo ảnh qua Replicate API với Midjourney-style model
        """
        try:
            headers = {
                "Authorization": f"Token {settings.replicate_api_token}",
                "Content-Type": "application/json"
            }
            
            # Sử dụng SDXL hoặc Midjourney-style model trên Replicate
            payload = {
                "version": "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
                "input": {
                    "prompt": f"{prompt} --style raw --quality 2 --ar 16:9",
                    "width": 1024,
                    "height": 576,
                    "num_outputs": 1,
                    "scheduler": "DPMSolverMultistep",
                    "num_inference_steps": 50,
                    "guidance_scale": 7.5
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.replicate.com/v1/predictions",
                    headers=headers,
                    json=payload
                ) as response:
                    
                    if response.status != 201:
                        raise Exception(f"Replicate API error: {response.status}")
                    
                    data = await response.json()
                    prediction_id = data["id"]
                    
                    # Poll cho đến khi hoàn thành
                    for _ in range(120):  # Max 10 minutes
                        await asyncio.sleep(5)
                        
                        async with session.get(
                            f"https://api.replicate.com/v1/predictions/{prediction_id}",
                            headers=headers
                        ) as status_response:
                            
                            status_data = await status_response.json()
                            
                            if status_data["status"] == "succeeded":
                                image_url = status_data["output"][0]
                                return await self._download_and_save_image(image_url, "replicate")
                            
                            elif status_data["status"] == "failed":
                                raise Exception("Replicate generation failed")
                    
                    raise Exception("Replicate generation timed out")
                    
        except Exception as e:
            logger.error(f"Lỗi khi tạo ảnh qua Replicate: {str(e)}")
            return None

    async def _generate_via_piapi(self, prompt: str) -> Optional[List[str]]:
        """
        Tạo ảnh qua Piapi.ai (Midjourney API service) với prompts đã tối ưu
        Trả về danh sách 4 URLs thay vì download file
        """
        try:
            headers = {
                "x-api-key": settings.piapi_api_key,
                "Content-Type": "application/json"
            }
            
            # Sử dụng prompt đã được tối ưu với Midjourney v7
            payload = {
                "model": "midjourney",
                "task_type": "imagine",
                "input": {
                    "prompt": f"{prompt} --v 7 --ar 16:9",
                    "aspect_ratio": "16:9",
                    "process_mode": "turbo",
                    "skip_prompt_check": False
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.piapi.ai/api/v1/task",
                    headers=headers,
                    json=payload
                ) as response:
                    
                    if response.status != 200:
                        raise Exception(f"Piapi error: {response.status}")
                    
                    data = await response.json()
                    
                    # Piapi trả về task_id trong data.task_id, không phải root level
                    if data.get("code") == 200 and "data" in data:
                        task_id = data["data"].get("task_id") or data["data"].get("id")
                    else:
                        task_id = data.get("task_id") or data.get("id")
                    
                    if not task_id:
                        raise Exception(f"Không nhận được task_id từ Piapi. Response: {data}")
                    
                    logger.info(f"Midjourney task started: {task_id}")
                    
                    # Poll for completion
                    for attempt in range(120):  # Max 10 minutes
                        await asyncio.sleep(5)
                        
                        async with session.get(
                            f"https://api.piapi.ai/api/v1/task/{task_id}",
                            headers=headers
                        ) as status_response:
                            
                            status_data = await status_response.json()
                            
                            # Piapi trả về: {code: 200, data: {status: "...", output: {...}}}
                            data = status_data.get("data", status_data)  # fallback to root if no data field
                            status = data.get("status")
                            
                            # Debug: Log response để kiểm tra
                            logger.info(f"Midjourney task {task_id} - Status: {status} (Attempt {attempt + 1}/120)")
                            if attempt <= 2:  # Chỉ log full response 2 lần đầu
                                logger.info(f"PIAPI RESPONSE: {status_data}")
                            
                            if status == "completed":
                                # Lấy URLs từ data.output field 
                                output = data.get("output", {})
                                
                                # Lấy image URLs từ Piapi response
                                image_urls = []
                                
                                # Ưu tiên image_urls (4 URLs riêng biệt từ Midjourney)
                                if "image_urls" in output and isinstance(output["image_urls"], list):
                                    image_urls = output["image_urls"]
                                    logger.info(f"✅ Tìm thấy {len(image_urls)} URLs trong output.image_urls")
                                
                                # Fallback 1: temporary_image_urls (processed URLs) 
                                elif "temporary_image_urls" in output and isinstance(output["temporary_image_urls"], list):
                                    image_urls = output["temporary_image_urls"]
                                    logger.info(f"✅ Sử dụng {len(image_urls)} temporary URLs")
                                
                                # Fallback 2: single image_url
                                elif "image_url" in output:
                                    image_urls = [output["image_url"]]
                                    logger.info("✅ Tìm thấy 1 URL trong output.image_url")
                                
                                # Validate URLs
                                if image_urls:
                                    valid_urls = [url for url in image_urls if url and isinstance(url, str) and url.startswith('http')]
                                    if valid_urls:
                                        logger.info(f"Midjourney trả về {len(valid_urls)} URLs hợp lệ: {valid_urls}")
                                        return valid_urls
                                    else:
                                        logger.error(f"Không có URLs hợp lệ. Raw URLs: {image_urls}")
                                        return None
                                else:
                                    logger.error(f"Không tìm thấy URLs trong output: {output}")
                                    return None
                            
                            elif status == "failed":
                                # Kiểm tra error object từ data.error
                                error_obj = data.get("error", {})
                                error_msg = error_obj.get("message") or error_obj.get("raw_message") or "Unknown error"
                                raise Exception(f"Midjourney generation failed: {error_msg}")
                            
                            elif status in ["processing", "pending", "queued", "running", "started"]:
                                # Tiếp tục polling cho các trạng thái đang chạy
                                continue
                            
                            elif status is None:
                                # Kiểm tra API error code
                                if status_data.get("code") != 200:
                                    error_msg = status_data.get("message", "API Error")
                                    raise Exception(f"Piapi API error: {error_msg}")
                                # Status None nhưng code 200 - tiếp tục đợi
                                continue
                            
                            else:
                                # Trạng thái không xác định khác, tiếp tục đợi
                                logger.warning(f"Unknown status: {status}, continuing...")
                                continue
                    
                    # Log chi tiết khi timeout
                    logger.error(f"Midjourney generation timed out after 10 minutes. Last response: {status_data}")
                    raise Exception("Midjourney generation timed out after 10 minutes")
                    
        except Exception as e:
            logger.error(f"Lỗi khi tạo ảnh qua Piapi: {str(e)}")
            return None

    async def _generate_via_goapi(self, prompt: str) -> Optional[str]:
        """
        Tạo ảnh qua GoAPI (Midjourney API service) với prompts đã tối ưu
        """
        try:
            headers = {
                "Authorization": f"Bearer {settings.goapi_token}",
                "Content-Type": "application/json"
            }
            
            # Sử dụng prompt đã được tối ưu bởi system prompt
            payload = {
                "prompt": f"{prompt} --ar 16:9 --v 6",
                "process_mode": "fast"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.goapi.ai/api/v1/midjourney/imagine",
                    headers=headers,
                    json=payload
                ) as response:
                    
                    if response.status != 200:
                        raise Exception(f"GoAPI error: {response.status}")
                    
                    data = await response.json()
                    task_id = data["task_id"]
                    
                    # Poll for completion
                    for _ in range(120):  # Max 10 minutes
                        await asyncio.sleep(5)
                        
                        async with session.get(
                            f"https://api.goapi.ai/api/v1/midjourney/task/{task_id}",
                            headers=headers
                        ) as status_response:
                            
                            status_data = await status_response.json()
                            
                            if status_data["status"] == "completed":
                                image_url = status_data["result"]["image_url"]
                                return await self._download_and_save_image(image_url, "midjourney")
                            
                            elif status_data["status"] == "failed":
                                raise Exception("GoAPI generation failed")
                    
                    raise Exception("GoAPI generation timed out")
                    
        except Exception as e:
            logger.error(f"Lỗi khi tạo ảnh qua GoAPI: {str(e)}")
            return None

    async def generate_single_image(self, prompt: str, use_midjourney: bool = False) -> Optional[GeneratedImages]:
        """
        Tạo một ảnh từ prompt với tùy chọn sử dụng Midjourney hoặc DALL-E
        Trả về GeneratedImages object với URLs từ Midjourney
        """
        try:
            if use_midjourney:
                # Ưu tiên Piapi.ai (Midjourney v7)
                if hasattr(settings, 'piapi_api_key') and settings.piapi_api_key:
                    logger.info("Sử dụng Piapi.ai (Midjourney v7) để tạo ảnh...")
                    result = await self._generate_via_piapi(prompt)
                    if result and isinstance(result, list):
                        # Tạo GeneratedImages object với danh sách URLs
                        generated_images = GeneratedImages(
                            midjourney_urls=result,
                            thumbnail_url=result[0] if result else None,  # URL đầu tiên làm thumbnail chính
                            image_generation_prompts=[prompt]
                        )
                        logger.info(f"Đã nhận {len(result)} URLs từ Midjourney: {result}")
                        return generated_images
                
                # Thử GoAPI nếu Piapi không thành công
                if hasattr(settings, 'goapi_token') and settings.goapi_token:
                    logger.info("Fallback to GoAPI...")
                    result = await self._generate_via_goapi(prompt)
                    if result:
                        return GeneratedImages(
                            thumbnail_url=result,
                            image_generation_prompts=[prompt]
                        )
                
                # Thử Replicate nếu GoAPI không thành công
                if hasattr(settings, 'replicate_api_token') and settings.replicate_api_token:
                    logger.info("Fallback to Replicate...")
                    result = await self._generate_via_replicate(prompt)
                    if result:
                        return GeneratedImages(
                            thumbnail_url=result,
                            image_generation_prompts=[prompt]
                        )
                
                # Không có fallback DALL-E nữa
                logger.warning("Tất cả Midjourney services không khả dụng, không thể tạo ảnh")
                
            # Bỏ qua DALL-E
            return None
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo ảnh đơn: {str(e)}")
            return None

    async def generate_multiple_images(
        self, 
        prompts: List[str], 
        include_thumbnail: bool = True,
        title: str = "",
        use_midjourney: bool = False
    ) -> GeneratedImages:
        """
        Tạo nhiều ảnh từ danh sách prompts với tối ưu hóa từ system prompts
        Trả về GeneratedImages với danh sách URLs từ Midjourney
        """
        try:
            logger.info(f"Bắt đầu tạo ảnh với Midjourney cho {len(prompts)} prompts")
            
            generated_images = GeneratedImages()
            
            # Nếu có title và prompts, sử dụng prompt đầu tiên để tạo ảnh chính
            if prompts and use_midjourney:
                main_prompt = prompts[0]
                logger.info(f"Tạo ảnh chính với prompt: {main_prompt[:100]}...")
                
                result = await self.generate_single_image(main_prompt, use_midjourney=True)
                
                if result and result.midjourney_urls:
                    # Gán tất cả URLs từ Midjourney
                    generated_images.midjourney_urls = result.midjourney_urls
                    generated_images.thumbnail_url = result.thumbnail_url
                    generated_images.image_generation_prompts = [main_prompt]
                    
                    logger.info(f"Đã tạo ảnh thành công với {len(result.midjourney_urls)} URLs từ Midjourney")
                    
                    # Thêm thông tin về tất cả ảnh vào additional_images
                    for i, url in enumerate(result.midjourney_urls):
                        generated_images.additional_images.append({
                            "url": url,
                            "filename": f"midjourney_image_{i+1}",
                            "prompt": main_prompt[:100]
                        })
                
                else:
                    logger.warning("Không thể tạo ảnh với Midjourney, trả về object rỗng")
            
            else:
                logger.warning("Không có prompts hoặc không sử dụng Midjourney")
            
            logger.info(f"Hoàn thành tạo ảnh: {len(generated_images.midjourney_urls)} URLs, {len(generated_images.additional_images)} additional images")
            return generated_images
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo nhiều ảnh: {str(e)}")
            # Trả về object rỗng thay vì raise exception
            return GeneratedImages()

    async def _download_and_save_image(self, image_url: str, source: str = "unknown") -> Optional[str]:
        """
        Download ảnh từ URL và lưu vào storage
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        
                        # Tạo tên file unique
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"{source}_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
                        filepath = os.path.join(self.storage_path, filename)
                        
                        # Lưu file
                        with open(filepath, 'wb') as f:
                            f.write(image_data)
                        
                        logger.info(f"Đã lưu ảnh: {filename}")
                        return filename
                    else:
                        logger.error(f"Không thể download ảnh: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Lỗi khi download và lưu ảnh: {str(e)}")
            return None

    async def _add_text_overlay(self, image_filename: str, text: str) -> Optional[str]:
        """
        Thêm text overlay lên thumbnail
        """
        try:
            input_path = os.path.join(self.storage_path, image_filename)
            
            if not os.path.exists(input_path):
                logger.error(f"File ảnh không tồn tại: {input_path}")
                return None
            
            # Mở ảnh
            with Image.open(input_path) as img:
                # Tạo copy để chỉnh sửa
                img_with_text = img.copy()
                draw = ImageDraw.Draw(img_with_text)
                
                # Thiết lập font (sử dụng font mặc định nếu không có font tùy chỉnh)
                font_size = max(40, img.width // 25)  # Tính font size dựa trên width
                try:
                    # Thử sử dụng font tùy chỉnh
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    # Fallback to default font
                    font = ImageFont.load_default()
                
                # Tính toán vị trí text (center)
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = (img.width - text_width) // 2
                y = img.height // 4  # Đặt ở 1/4 chiều cao từ trên
                
                # Vẽ shadow (outline) cho text
                shadow_offset = 2
                for dx in [-shadow_offset, 0, shadow_offset]:
                    for dy in [-shadow_offset, 0, shadow_offset]:
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text, font=font, fill="black")
                
                # Vẽ text chính
                draw.text((x, y), text, font=font, fill="white")
                
                # Tạo tên file mới
                name_parts = image_filename.split('.')
                new_filename = f"{name_parts[0]}_overlay.{name_parts[1]}"
                output_path = os.path.join(self.storage_path, new_filename)
                
                # Lưu ảnh mới
                img_with_text.save(output_path, quality=95)
                
                logger.info(f"Đã thêm text overlay: {new_filename}")
                return new_filename
                
        except Exception as e:
            logger.error(f"Lỗi khi thêm text overlay: {str(e)}")
            return None

# Singleton instance
image_generator = ImageGenerator() 