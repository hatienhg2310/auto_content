import openai
import json
import asyncio
import re
from typing import List, Dict, Any, Tuple, Optional
import sys
import pathlib

# Thêm thư mục gốc vào sys.path
root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.models import InputData, GeneratedContent, WorkflowConfig
from config.settings import settings
from src.prompt_manager import prompt_manager
import logging
import httpx
import os

logger = logging.getLogger(__name__)


class AIContentGenerator:
    """
    Dịch vụ tạo nội dung AI sử dụng Gemini API (chính) và OpenAI (dự phòng) với system prompts chuyên biệt
    """
    
    def __init__(self):
        # Cấu hình Gemini API (ưu tiên)
        self.gemini_api_key = settings.gemini_api_key
        self.gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        self.use_gemini = bool(self.gemini_api_key and self.gemini_api_key != "your-gemini-api-key")
        
        if self.use_gemini:
            logger.info("Đã khởi tạo Gemini REST API")
        else:
            logger.warning("Gemini API key không khả dụng, sử dụng OpenAI")
        
        # Cấu hình OpenAI (dự phòng)
        http_client = httpx.AsyncClient()
        self.openai_client = openai.AsyncOpenAI(api_key=settings.openai_api_key, http_client=http_client)
        
        self.config = WorkflowConfig()
        self.prompt_manager = prompt_manager
        
        # Title diversity tracking để tránh repetition
        self.recent_title_starts = []  # Track recent starting words
        self.max_diversity_history = 20  # Remember last 20 titles
        
        # Tag diversity tracking để tránh repetition
        self.recent_tag_patterns = []  # Track recent tag patterns
        self.max_tag_diversity_history = 15  # Remember last 15 tag sets
    
    async def _generate_with_gemini(self, prompt: str, temperature: float = 0.8) -> str:
        """Tạo nội dung bằng Gemini REST API"""
        try:
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": temperature,  # Tăng temperature cho creativity
                    "topK": 40,
                    "topP": 0.95,
                    "maxOutputTokens": 2048,
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.gemini_url}?key={self.gemini_api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise Exception(f"Gemini API error: {response.status_code} - {response.text}")
                
                result = response.json()
                
                if "candidates" not in result or not result["candidates"]:
                    raise Exception("Gemini không trả về candidates")
                
                content = result["candidates"][0]["content"]["parts"][0]["text"]
                return content.strip()
                
        except Exception as e:
            logger.error(f"Lỗi Gemini API: {str(e)}")
            raise
    
    async def _generate_with_openai(self, prompt: str, temperature: float = 0.8) -> str:
        """Tạo nội dung bằng OpenAI API (dự phòng)"""
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.config.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,  # Tăng temperature cho creativity
                max_tokens=2000,
                top_p=0.95
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Lỗi OpenAI API: {str(e)}")
            raise
    
    async def _generate_content(self, prompt: str, temperature: float = 0.8) -> str:
        """Tạo nội dung với AI (ưu tiên Gemini, dự phòng OpenAI)"""
        if self.use_gemini:
            try:
                logger.info("Sử dụng Gemini API để tạo nội dung")
                return await self._generate_with_gemini(prompt, temperature)
            except Exception as e:
                logger.warning(f"Gemini API lỗi, chuyển sang OpenAI: {str(e)}")
                return await self._generate_with_openai(prompt, temperature)
        else:
            logger.info("Sử dụng OpenAI API để tạo nội dung")
            return await self._generate_with_openai(prompt, temperature)

    def _create_content_generation_prompt(self, input_data: InputData) -> str:
        """Tạo prompt để generate nội dung - legacy method, giữ lại cho compatibility"""
        return self.prompt_manager.get_integrated_content_prompt(
            channel_name=input_data.channel_name,
            channel_description=input_data.channel_description,
            video_topic=input_data.video_topic or "Tạo nội dung phù hợp với kênh",
            additional_context=input_data.additional_context or ""
        )
    
    def _track_title_diversity(self, title: str):
        """Track title starting words to ensure diversity"""
        if title:
            first_word = title.split()[0].lower() if title.split() else ""
            if first_word:
                self.recent_title_starts.append(first_word)
                # Giữ chỉ N titles gần nhất
                if len(self.recent_title_starts) > self.max_diversity_history:
                    self.recent_title_starts.pop(0)
    
    def _is_title_diverse(self, title: str) -> bool:
        """Check if title is diverse enough compared to recent titles"""
        if not title or not self.recent_title_starts:
            return True
            
        first_word = title.split()[0].lower() if title.split() else ""
        if not first_word:
            return True
            
        # Count occurrences of this first word in recent history
        recent_count = self.recent_title_starts.count(first_word)
        
        # Allow max 2 times same starting word in last 20 titles (10% repetition)
        max_allowed = max(1, self.max_diversity_history // 10)
        
        return recent_count < max_allowed
    
    def _get_diversity_instruction(self) -> str:
        """Generate instruction to avoid repetitive starting words"""
        if len(self.recent_title_starts) < 3:
            return ""
            
        # Get most common starting words
        from collections import Counter
        common_starts = Counter(self.recent_title_starts).most_common(5)
        
        if common_starts:
            avoid_words = [word for word, count in common_starts if count > 1]
            if avoid_words:
                return f"\n\n🚨 DIVERSITY REQUIREMENT: DO NOT start the title with these overused words: {', '.join(avoid_words)}. Use creative, fresh starting words to ensure variety!"
        
        return ""

    def _track_tag_diversity(self, tags: List[str]):
        """Track tag patterns to ensure diversity"""
        if tags:
            # Extract first words from tags for pattern analysis
            tag_patterns = []
            full_tags = []
            
            for tag in tags:
                if tag:
                    # Track first word patterns
                    first_word = tag.split()[0].lower() if tag.split() else ""
                    if first_word:
                        tag_patterns.append(first_word)
                    
                    # Track full tags (normalized)
                    full_tag = tag.lower().strip()
                    if full_tag:
                        full_tags.append(full_tag)
            
            if tag_patterns:
                self.recent_tag_patterns.append(tag_patterns)
                # Giữ chỉ N tag sets gần nhất
                if len(self.recent_tag_patterns) > self.max_tag_diversity_history:
                    self.recent_tag_patterns.pop(0)
            
            # ENHANCED: Also track full tags for exact duplicate detection
            if full_tags:
                if not hasattr(self, 'recent_full_tags'):
                    self.recent_full_tags = []
                
                self.recent_full_tags.append(full_tags)
                # Giữ chỉ N full tag sets gần nhất
                if len(self.recent_full_tags) > self.max_tag_diversity_history:
                    self.recent_full_tags.pop(0)
    
    def _is_tags_diverse(self, tags: List[str]) -> bool:
        """Check if tags are diverse enough compared to recent tag sets"""
        if not tags or not self.recent_tag_patterns:
            return True
            
        # ENHANCED: Extract both first words and full tag patterns for better diversity checking
        current_patterns = []
        current_full_tags = []
        
        for tag in tags:
            if tag:
                # Track first word patterns
                first_word = tag.split()[0].lower() if tag.split() else ""
                if first_word:
                    current_patterns.append(first_word)
                
                # Track full tag patterns (normalized)
                full_tag = tag.lower().strip()
                if full_tag:
                    current_full_tags.append(full_tag)
        
        if not current_patterns and not current_full_tags:
            return True
            
        # Count how many patterns overlap with recent history
        all_recent_patterns = []
        all_recent_full_tags = []
        
        for pattern_set in self.recent_tag_patterns:
            all_recent_patterns.extend(pattern_set)
            
        # Also track full tags from recent history (if available)
        if hasattr(self, 'recent_full_tags'):
            for tag_set in self.recent_full_tags:
                all_recent_full_tags.extend(tag_set)
        
        from collections import Counter
        recent_counter = Counter(all_recent_patterns)
        recent_full_counter = Counter(all_recent_full_tags)
        
        # Check if too many current patterns are overused
        overused_count = 0
        duplicate_full_tags = 0
        
        # Check first word patterns
        for pattern in current_patterns:
            if recent_counter.get(pattern, 0) >= 2:  # Reduced threshold from 3 to 2
                overused_count += 1
        
        # Check full tag duplicates
        for full_tag in current_full_tags:
            if recent_full_counter.get(full_tag, 0) >= 1:  # No exact duplicates allowed
                duplicate_full_tags += 1
        
        # ENHANCED: More strict diversity requirements
        # Allow max 20% overlap with overused patterns (reduced from 30%)
        max_allowed_overlap = max(1, len(current_patterns) // 5)
        
        # No exact duplicate tags allowed
        max_allowed_duplicates = 0
        
        is_diverse = (overused_count <= max_allowed_overlap and 
                     duplicate_full_tags <= max_allowed_duplicates)
        
        if not is_diverse:
            logger.info(f"Tags not diverse: {overused_count} overused patterns (max {max_allowed_overlap}), "
                       f"{duplicate_full_tags} duplicate tags (max {max_allowed_duplicates})")
        
        return is_diverse
    
    def _get_tag_diversity_instruction(self) -> str:
        """Generate instruction to avoid repetitive tag patterns"""
        if len(self.recent_tag_patterns) < 2:  # Reduced threshold
            return ""
            
        # Get most common tag patterns
        all_recent_patterns = []
        all_recent_full_tags = []
        
        for pattern_set in self.recent_tag_patterns:
            all_recent_patterns.extend(pattern_set)
            
        # Also get full tags if available
        if hasattr(self, 'recent_full_tags'):
            for tag_set in self.recent_full_tags:
                all_recent_full_tags.extend(tag_set)
        
        from collections import Counter
        common_patterns = Counter(all_recent_patterns).most_common(10)
        common_full_tags = Counter(all_recent_full_tags).most_common(10)
        
        instruction_parts = []
        
        # Avoid overused starting words
        if common_patterns:
            avoid_patterns = [pattern for pattern, count in common_patterns if count >= 2]  # Reduced threshold
            if avoid_patterns:
                instruction_parts.append(f"🚨 AVOID these overused starting words: {', '.join(avoid_patterns[:5])}")
        
        # Avoid exact duplicate tags
        if common_full_tags:
            avoid_full_tags = [tag for tag, count in common_full_tags if count >= 1]
            if avoid_full_tags:
                instruction_parts.append(f"🚨 NEVER repeat these exact tags: {', '.join(avoid_full_tags[:5])}")
        
        if instruction_parts:
            diversity_instruction = f"\n\n🎯 TAG DIVERSITY REQUIREMENTS:\n" + "\n".join(instruction_parts)
            diversity_instruction += f"\n\n💡 CREATIVITY BOOST: Use synonyms, different word orders, and fresh variations. Examples:"
            diversity_instruction += f"\n- Instead of 'relaxing music' → try 'calming sounds', 'peaceful melodies', 'soothing audio'"
            diversity_instruction += f"\n- Instead of 'meditation music' → try 'mindfulness sounds', 'zen audio', 'spiritual music'"
            diversity_instruction += f"\n- Instead of 'sleep music' → try 'bedtime sounds', 'night relaxation', 'dream music'"
            return diversity_instruction
        
        return ""

    async def _generate_title_and_thumbnail(self, input_data: InputData, image_base64: Optional[str] = None) -> Dict[str, str]:
        """
        Tạo title và thumbnail text sử dụng system prompt chuyên biệt với diversity enhancement
        """
        max_attempts = 3  # Try up to 3 times for diverse title
        
        for attempt in range(max_attempts):
            try:
                image_context = ""
                if image_base64:
                    image_context = "Image provided for analysis"
                
                # Sử dụng system prompt chuyên biệt cho title
                title_prompt = self.prompt_manager.get_title_generation_prompt(
                    channel_name=input_data.channel_name,
                    channel_description=input_data.channel_description,
                    video_topic=input_data.video_topic or "Tạo nội dung phù hợp với kênh",
                    image_context=image_context
                )
                
                # Thêm diversity instruction để tránh repetition
                diversity_instruction = self._get_diversity_instruction()
                title_prompt += diversity_instruction
                
                # Xây dựng message payload
                user_content = [{"type": "text", "text": title_prompt}]
                
                if image_base64:
                    user_content.insert(0, {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high"
                        }
                    })
                
                messages = [
                    {
                        "role": "system", 
                        "content": "You are ThumbnailCraft-Pro, an expert YouTube title SEO specialist. Follow the system prompt exactly and ensure title diversity."
                    },
                    {"role": "user", "content": user_content}
                ]
                
                # Tạo prompt cho Gemini/OpenAI với higher temperature cho creativity
                full_prompt = f"{messages[0]['content']}\n\n{title_prompt}"
                if image_base64:
                    full_prompt = f"[Ảnh được cung cấp để phân tích]\n\n{full_prompt}"
                
                # Tăng temperature cho title generation để tăng creativity
                creative_temp = 0.9 + (attempt * 0.05)  # Increase temp with each attempt
                response_text = await self._generate_content(full_prompt, temperature=creative_temp)
                
                # Parse response để lấy title và thumbnail text
                title = ""
                thumbnail_text = ""
                
                lines = response_text.split('\n')
                for i, line in enumerate(lines):
                    if "**OPTIMIZED TITLE:**" in line:
                        # Lấy title từ dòng tiếp theo hoặc cùng dòng
                        if i + 1 < len(lines):
                            title = lines[i + 1].strip()
                        else:
                            title = line.split("**OPTIMIZED TITLE:**")[-1].strip()
                    elif "**THUMBNAIL TEXT:**" in line:
                        # Lấy thumbnail text từ dòng tiếp theo hoặc cùng dòng
                        if i + 1 < len(lines):
                            thumbnail_text = lines[i + 1].strip()
                        else:
                            thumbnail_text = line.split("**THUMBNAIL TEXT:**")[-1].strip()
                
                # Fallback parsing nếu format không chuẩn
                if not title:
                    title_match = response_text.split("🎯")[1].split("🖼️")[0] if "🎯" in response_text else response_text[:100]
                    title = title_match.strip().replace("**OPTIMIZED TITLE:**", "").strip()
                
                if not thumbnail_text:
                    thumb_match = response_text.split("🖼️")[-1] if "🖼️" in response_text else "ENGAGING"
                    thumbnail_text = thumb_match.replace("**THUMBNAIL TEXT:**", "").strip()
                
                # Check diversity
                if self._is_title_diverse(title):
                    # Title is diverse enough, track it and return
                    self._track_title_diversity(title)
                    
                    logger.info(f"Generated diverse title (attempt {attempt + 1}): {title}")
                    logger.info(f"Generated thumbnail text: {thumbnail_text}")
                    
                    return {
                        "title": title,
                        "thumbnail_text": thumbnail_text
                    }
                else:
                    logger.warning(f"Title not diverse enough (attempt {attempt + 1}): {title}")
                    if attempt < max_attempts - 1:
                        continue  # Try again with higher temperature
                
            except Exception as e:
                logger.error(f"Lỗi khi tạo title (attempt {attempt + 1}): {str(e)}")
                if attempt < max_attempts - 1:
                    continue  # Try again
        
        # Fallback if all attempts failed or not diverse enough
        fallback_title = f"{input_data.video_topic} | {input_data.channel_name}"
        self._track_title_diversity(fallback_title)
        
        logger.warning(f"Using fallback title: {fallback_title}")
        return {
            "title": fallback_title,
            "thumbnail_text": "WATCH NOW"
        }

    async def generate_optimized_content(self, input_data: InputData, image_base64: Optional[str] = None) -> GeneratedContent:
        """
        Tạo nội dung tối ưu sử dụng system prompts chuyên biệt với title diversity
        """
        try:
            logger.info(f"Bắt đầu tạo nội dung tối ưu cho kênh: {input_data.channel_name}")
            
            # Bước 1: Tạo title và thumbnail text với system prompt chuyên biệt và diversity checking
            title_data = await self._generate_title_and_thumbnail(input_data, image_base64)
            
            # Bước 2: Tạo description với system prompt chuyên biệt
            description = await self._generate_description(title_data["title"], input_data)
            
            # Bước 3: Tạo tags (có thể sử dụng system prompt riêng nếu có)
            tags = await self._generate_tags(title_data["title"], description, input_data)
            
            # Bước 4: Tạo image prompts với Midjourney generator
            image_prompts = await self._generate_image_prompts(title_data["title"], tags[:4])
            
            # Tạo GeneratedContent object
            generated_content = GeneratedContent(
                title=title_data["title"][:self.config.max_title_length],
                description=description[:self.config.max_description_length],
                tags=tags[:self.config.number_of_tags],
                thumbnail_name=title_data["thumbnail_text"],
                image_prompts=image_prompts
            )
            
            logger.info(f"Đã tạo thành công nội dung tối ưu cho: {generated_content.title}")
            return generated_content
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo nội dung tối ưu: {str(e)}")
            # Fallback về method cũ
            return await self.generate_content(input_data, image_base64)
    
    async def _generate_description(self, title: str, input_data: InputData) -> str:
        """
        Tạo description sử dụng system prompt chuyên biệt
        """
        try:
            channel_context = f"{input_data.channel_name} - {input_data.channel_description}"
            
            description_prompt = self.prompt_manager.get_description_generation_prompt(
                title=title,
                channel_context=channel_context
            )
            
            messages = [
                {
                    "role": "system", 
                    "content": "You are an expert YouTube SEO copywriter. Generate comprehensive, engaging descriptions following the system prompt guidelines."
                },
                {"role": "user", "content": description_prompt}
            ]
            
            # Tạo prompt đầy đủ cho Gemini/OpenAI
            full_prompt = f"{messages[0]['content']}\n\n{description_prompt}"
            description = await self._generate_content(full_prompt)
            logger.info(f"Generated description length: {len(description)} characters")
            
            return description
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo description: {str(e)}")
            # Fallback description
            return f"""Discover amazing content about {input_data.video_topic} on {input_data.channel_name}!

{input_data.channel_description}

🎯 Perfect for:
- Learning and entertainment
- High-quality content experience  
- Engaging video content

Subscribe for more amazing videos!

#content #youtube #video #amazing"""
    
    async def _generate_tags(self, title: str, description: str, input_data: InputData) -> List[str]:
        """
        Tạo tags tối ưu với diversity tracking và system prompt chuyên biệt
        """
        max_attempts = 3  # Try up to 3 times for diverse tags
        
        for attempt in range(max_attempts):
            try:
                channel_context = f"{input_data.channel_name} - {input_data.channel_description}"
                
                # Sử dụng system prompt chuyên biệt cho tags
                tags_prompt = self.prompt_manager.get_tags_generation_prompt(
                    title=title,
                    description=description,
                    channel_context=channel_context
                )
                
                # Thêm diversity instruction để tránh repetition
                diversity_instruction = self._get_tag_diversity_instruction()
                tags_prompt += diversity_instruction
                
                # Tăng temperature cho attempts sau để tăng creativity
                temperature = 0.9 + (attempt * 0.05)
                
                # Tạo nội dung với temperature cao hơn cho tags
                tags_response = await self._generate_content(tags_prompt, temperature)
                
                # Parse JSON response với nhiều fallback methods
                tags = self._parse_tags_response(tags_response)
                
                if tags:
                    # Clean và validate tags
                    tags = self._clean_and_validate_tags(tags)
                    
                    # Check diversity
                    if self._is_tags_diverse(tags):
                        logger.info(f"Generated {len(tags)} diverse tags on attempt {attempt + 1}")
                        
                        # Track for future diversity
                        self._track_tag_diversity(tags)
                        
                        return tags
                    else:
                        logger.info(f"Tags not diverse enough on attempt {attempt + 1}, retrying...")
                        continue
                else:
                    logger.warning(f"No tags generated on attempt {attempt + 1}")
                    continue
                    
            except Exception as e:
                logger.error(f"Lỗi khi tạo tags (attempt {attempt + 1}): {str(e)}")
                continue
        
        # Fallback tags if all attempts fail
        logger.warning("All tag generation attempts failed, using fallback tags")
        fallback_tags = self._generate_fallback_tags(input_data, title)
        
        # Still track fallback tags for diversity
        self._track_tag_diversity(fallback_tags)
        
        return fallback_tags
    
    def _parse_tags_response(self, tags_response: str) -> List[str]:
        """Parse tags from AI response with multiple fallback methods"""
        try:
            # Method 1: Direct JSON parsing
            tags_data = json.loads(tags_response)
            
            if isinstance(tags_data, list):
                return tags_data
            elif isinstance(tags_data, dict) and 'tags' in tags_data:
                return tags_data['tags']
            else:
                # Try to get first list value
                for value in tags_data.values():
                    if isinstance(value, list):
                        return value
                        
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract JSON array from text
        import re
        json_match = re.search(r'\{[^}]*"tags":\s*\[([^\]]+)\][^}]*\}', tags_response, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group(0)
                tags_data = json.loads(json_str)
                return tags_data.get('tags', [])
            except:
                pass
        
        # Method 3: Extract array from text
        array_match = re.search(r'\[([^\]]+)\]', tags_response, re.DOTALL)
        if array_match:
            try:
                array_str = f"[{array_match.group(1)}]"
                return json.loads(array_str)
            except:
                pass
        
        # Method 4: Split by comma and clean
        lines = tags_response.split('\n')
        tags = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('*'):
                # Remove quotes and extra characters
                clean_line = re.sub(r'^["\'\-\*\d\.\s]+', '', line)
                clean_line = re.sub(r'["\'\,\.\s]*$', '', clean_line)  # Also remove periods
                
                # ENHANCED: Remove ALL periods and punctuation throughout the line
                clean_line = re.sub(r'[\.]+', '', clean_line)  # Remove all periods
                clean_line = re.sub(r'[,]+', '', clean_line)   # Remove all commas
                
                # Remove other punctuation except hyphens and spaces
                import string
                clean_line = ''.join(char for char in clean_line if char not in string.punctuation or char in ['-', ' '])
                
                # CRITICAL: Convert to single word format like YouTube expects
                # Remove spaces and hyphens to create compound words
                clean_line = clean_line.replace(' ', '').replace('-', '')
                clean_line = clean_line.strip()
                
                if clean_line and len(clean_line) > 2:
                    tags.append(clean_line)
        
        return tags[:15]  # Limit to 15 tags
    
    def _clean_and_validate_tags(self, tags: List[str]) -> List[str]:
        """Clean and validate tags - convert to single word format like YouTube expects"""
        cleaned_tags = []
        
        for tag in tags:
            if not tag or not isinstance(tag, str):
                continue
                
            # Clean tag - remove all punctuation and special characters
            clean_tag = tag.strip().lower()
            
            # Remove leading numbers, bullets, quotes, hashes, etc.
            clean_tag = re.sub(r'^[#\-\*\d\.\s"\'\(\)\[\]]+', '', clean_tag)
            
            # Remove trailing punctuation, quotes, commas, periods, etc.
            clean_tag = re.sub(r'["\'\,\.\!\?\;\:\(\)\[\]\s]*$', '', clean_tag)
            
            # ENHANCED: Remove ALL punctuation marks throughout the tag
            # Remove periods, commas, and all special characters
            clean_tag = re.sub(r'[\.]+', '', clean_tag)  # Remove all periods
            clean_tag = re.sub(r'[,]+', '', clean_tag)   # Remove all commas
            clean_tag = re.sub(r'[!@#$%^&*()_+=\[\]{}|;:\'",.<>?/\\`~]+', '', clean_tag)  # Remove special chars
            
            # ENHANCED: Also remove any remaining punctuation that might be missed
            import string
            # Remove all punctuation except hyphens (which will be removed later)
            clean_tag = ''.join(char for char in clean_tag if char not in string.punctuation or char in ['-', ' '])
            
            # CRITICAL: Convert multi-word tags to single compound words (YouTube format)
            # Remove spaces and hyphens to create compound words
            clean_tag = clean_tag.replace(' ', '').replace('-', '')
            
            # Remove any remaining whitespace
            clean_tag = clean_tag.strip()
            
            # Additional validation with enhanced stop words list
            stop_words = [
                'youtube', 'video', 'content', 'amazing', 'subscribe', 'like', 'share', 'comment',
                'with', 'and', 'the', 'for', 'of', 'in', 'to', 'a', 'an', 'is', 'are', 'was', 'were',
                'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                'could', 'should', 'may', 'might', 'must', 'can', 'tag', 'tags', 'watch', 'now'
            ]
            
            # Validate the cleaned tag
            if (clean_tag and 
                len(clean_tag) >= 2 and 
                len(clean_tag) <= 50 and
                clean_tag not in cleaned_tags and
                not clean_tag.startswith('tag') and
                clean_tag not in stop_words and
                not clean_tag.isdigit() and  # Exclude pure numbers
                len(clean_tag) >= 2):  # Must have at least 2 characters
                cleaned_tags.append(clean_tag)
        
        return cleaned_tags[:15]  # Limit to 15 tags
    
    def _generate_fallback_tags(self, input_data: InputData, title: str) -> List[str]:
        """Generate fallback tags based on input data - single word format"""
        fallback_tags = []
        
        # Add channel-based tags (remove spaces and punctuation)
        if input_data.channel_name:
            channel_tag = input_data.channel_name.lower().replace(" ", "").replace(".", "").replace(",", "")
            if channel_tag and len(channel_tag) > 2:
                fallback_tags.append(channel_tag)
        
        # Add topic-based tags (single words only)
        if input_data.video_topic:
            topic_words = input_data.video_topic.lower().split()
            stop_words = ['with', 'and', 'the', 'for', 'of', 'in', 'to', 'a', 'an', 'is', 'are', 'was', 'were']
            for word in topic_words:
                # Clean word and remove punctuation
                clean_word = word.replace(".", "").replace(",", "").replace("!", "").replace("?", "")
                if len(clean_word) > 2 and clean_word not in fallback_tags and clean_word not in stop_words:
                    fallback_tags.append(clean_word)
        
        # Add title-based tags (single words only)
        if title:
            title_words = title.lower().split()
            stop_words = ['with', 'and', 'the', 'for', 'of', 'in', 'to', 'a', 'an', 'is', 'are', 'was', 'were']
            for word in title_words:
                # Clean word and remove punctuation
                clean_word = word.replace(".", "").replace(",", "").replace("!", "").replace("?", "")
                if len(clean_word) > 2 and clean_word not in fallback_tags and clean_word not in stop_words:
                    fallback_tags.append(clean_word)
        
        # Add common relaxation tags (SINGLE WORD FORMAT like your examples)
        relaxation_tags = [
            "music", "relax", "healingmusic", "piano", "watersounds", 
            "relaxingcalming", "helios4k", "sleepmusic", "innerpeace", 
            "relaxingmusic", "meditation", "mindfulness", "peaceful", 
            "nature", "ambient", "calming", "soothing", "zen", "spa"
        ]
        
        for tag in relaxation_tags:
            if tag not in fallback_tags:
                fallback_tags.append(tag)
                if len(fallback_tags) >= 12:
                    break
        
        return fallback_tags[:12]
    
    async def _generate_image_prompts(self, title: str, keywords: List[str]) -> List[str]:
        """
        Tạo image prompts sử dụng Midjourney system prompt
        """
        try:
            midjourney_prompt = self.prompt_manager.get_midjourney_generation_prompt(
                title=title,
                keywords=keywords
            )
            
            messages = [
                {
                    "role": "system", 
                    "content": "You are ThumbnailCraft-Pro. Generate 3 cinematic Midjourney prompts for YouTube thumbnails with negative space for text overlays."
                },
                {"role": "user", "content": midjourney_prompt}
            ]
            
            # Tạo prompt cho Gemini/OpenAI
            full_prompt = f"{messages[0]['content']}\n\n{midjourney_prompt}"
            response_text = await self._generate_content(full_prompt)
            
            # Parse prompts từ response
            prompts = []
            
            # Tìm các prompt trong code blocks
            import re
            code_blocks = re.findall(r'```(.*?)```', response_text, re.DOTALL)
            
            for block in code_blocks:
                if block.strip() and not block.strip().startswith('json'):
                    prompts.append(block.strip())
            
            # Nếu không tìm thấy code blocks, parse theo format khác
            if not prompts:
                lines = response_text.split('\n')
                for line in lines:
                    if 'PROMPT' in line.upper() and ':' in line:
                        continue
                    elif line.strip() and len(line.strip()) > 50:  # Prompts thường dài
                        prompts.append(line.strip())
            
            # Đảm bảo có ít nhất 3 prompts
            while len(prompts) < 3:
                fallback_prompt = f"cinematic {title.lower()}, professional lighting, 16:9 composition, negative space for text overlay, high quality photography --ar 16:9 --v 7"
                prompts.append(fallback_prompt)
            
            logger.info(f"Generated {len(prompts)} image prompts")
            return prompts[:3]  # Chỉ lấy 3 prompts
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo image prompts: {str(e)}")
            # Fallback prompts
            return [
                f"cinematic scene related to {title}, professional lighting, shallow depth of field, 16:9 aspect ratio --ar 16:9 --v 7",
                f"artistic composition for {title}, dramatic lighting, negative space for text, high quality --ar 16:9 --v 7",
                f"professional thumbnail style for {title}, engaging visual, text overlay space, modern design --ar 16:9 --v 7"
            ]

    async def generate_content(self, input_data: InputData, image_base64: Optional[str] = None) -> GeneratedContent:
        """
        Tạo nội dung cho video YouTube - method chính với tích hợp system prompts
        """
        try:
            logger.info(f"Bắt đầu tạo nội dung cho kênh: {input_data.channel_name}")
            
            # Ưu tiên sử dụng method tối ưu với system prompts
            return await self.generate_optimized_content(input_data, image_base64)
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo nội dung: {str(e)}")
            # Fallback về method cũ nếu có lỗi
            try:
                text_prompt = self._create_content_generation_prompt(input_data)
                
                # Xây dựng message payload
                user_content = [{"type": "text", "text": text_prompt}]
                
                if image_base64:
                    logger.info("Phát hiện có ảnh, thêm dữ liệu ảnh vào prompt.")
                    user_content.insert(0, {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high"
                        }
                    })
                
                messages = [
                    {
                        "role": "system", 
                        "content": "Bạn là chuyên gia tạo nội dung YouTube và phân tích hình ảnh. Luôn trả về định dạng JSON chính xác."
                    },
                    {"role": "user", "content": user_content}
                ]
                
                # Sử dụng model hỗ trợ vision
                model = "gpt-4-turbo"

                response = await self.openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.8,
                    max_tokens=2000,
                    response_format={"type": "json_object"}
                )
                
                content_json = response.choices[0].message.content.strip()
                
                # Parse JSON response
                try:
                    content_data = json.loads(content_json)
                except json.JSONDecodeError:
                    # Nếu response không phải JSON hợp lệ, thử extract JSON từ text
                    import re
                    json_match = re.search(r'\{.*\}', content_json, re.DOTALL)
                    if json_match:
                        content_data = json.loads(json_match.group())
                    else:
                        raise ValueError("Không thể parse JSON từ AI response")
                
                # Validate và tạo GeneratedContent object
                generated_content = GeneratedContent(
                    title=content_data.get("title", "")[:self.config.max_title_length],
                    description=content_data.get("description", "")[:self.config.max_description_length],
                    tags=content_data.get("tags", [])[:self.config.number_of_tags],
                    thumbnail_name=content_data.get("thumbnail_name", ""),
                    image_prompts=content_data.get("image_prompts", [])
                )
                
                logger.info(f"Đã tạo thành công nội dung (fallback) cho: {generated_content.title}")
                return generated_content
                
            except Exception as fallback_error:
                logger.error(f"Lỗi cả method fallback: {str(fallback_error)}")
                raise
    
    async def generate_improved_prompts(self, base_prompts: List[str], context: str = "") -> List[str]:
        """
        Cải thiện prompts để tạo ảnh tốt hơp - sử dụng Midjourney system prompt
        """
        try:
            # Sử dụng Midjourney prompt generator để cải thiện
            if len(base_prompts) > 0:
                # Extract keywords từ context và prompts
                keywords = context.split()[:4] if context else ["professional", "cinematic", "high-quality", "engaging"]
                
                # Tạo title giả từ context
                title = context.split('-')[0].strip() if '-' in context else "Professional Content"
                
                improved_prompts = await self._generate_image_prompts(title, keywords)
                
                logger.info(f"Đã cải thiện {len(improved_prompts)} prompts bằng Midjourney generator")
                return improved_prompts
            
            return base_prompts
            
        except Exception as e:
            logger.error(f"Lỗi khi cải thiện prompts: {str(e)}")
            return base_prompts  # Trả về prompts gốc nếu có lỗi
    
    async def generate_parallel_content(
        self, 
        input_data: InputData, 
        image_base64: Optional[str] = None
    ) -> Tuple[GeneratedContent, List[str]]:
        """
        Tạo nội dung và cải thiện prompts song song - sử dụng system prompts tối ưu
        """
        try:
            # Tạo nội dung chính với system prompts
            content = await self.generate_optimized_content(input_data, image_base64=image_base64)
            
            # Prompts đã được tối ưu trong quá trình tạo nội dung
            improved_prompts = content.image_prompts
            
            return content, improved_prompts
            
        except Exception as e:
            logger.error(f"Lỗi trong quá trình tạo nội dung song song: {str(e)}")
            raise


    async def generate_content_variations(
        self, 
        input_data_list: List[InputData], 
        image_base64: Optional[str] = None
    ) -> List[GeneratedContent]:
        """
        Tạo nhiều variations của content từ danh sách input data
        Mỗi content sẽ có approach khác nhau để đảm bảo đa dạng
        """
        try:
            logger.info(f"Bắt đầu tạo {len(input_data_list)} content variations")
            
            # Tạo các approach khác nhau cho mỗi variation
            approaches = [
                "detailed_analysis",    # Phân tích chi tiết
                "quick_guide",         # Hướng dẫn nhanh
                "beginner_tips",       # Tips cho người mới
                "advanced_insights",   # Góc nhìn nâng cao
                "practical_tutorial"   # Tutorial thực hành
            ]
            
            tasks = []
            for i, input_data in enumerate(input_data_list):
                # Modify context based on approach
                approach = approaches[i % len(approaches)]
                
                # Tạo modified input với approach khác nhau
                modified_input = InputData(
                    channel_id=input_data.channel_id,
                    channel_name=input_data.channel_name,
                    channel_description=input_data.channel_description,
                    video_topic=input_data.video_topic,
                    additional_context=f"{input_data.additional_context or ''} | Style: {approach} | Make content unique and different",
                    video_frame_file=input_data.video_frame_file,
                    video_frame_url=input_data.video_frame_url,
                    created_by=input_data.created_by,
                    created_at=input_data.created_at
                )
                
                # Tạo task cho mỗi variation
                task = self.generate_optimized_content(modified_input, image_base64)
                tasks.append(task)
            
            # Chạy tất cả tasks song song
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Lọc ra kết quả thành công
            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Lỗi tạo variation {i+1}: {str(result)}")
                else:
                    successful_results.append(result)
                    logger.info(f"✅ Variation {i+1}: {result.title[:50]}...")
            
            logger.info(f"Đã tạo thành công {len(successful_results)}/{len(input_data_list)} content variations")
            return successful_results
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo content variations: {str(e)}")
            return []


# Singleton instance
ai_generator = AIContentGenerator() 