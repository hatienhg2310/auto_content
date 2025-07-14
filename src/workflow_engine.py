import asyncio
import uuid
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
import base64
import os
import sys
import pathlib
from slugify import slugify

# Thêm thư mục gốc vào sys.path
root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.models import (
    InputData, ContentPackage, ContentStatus, 
    GeneratedContent, GeneratedImages, WorkflowConfig, ChannelConfig
)
from src.ai_service import ai_generator
from src.image_service import image_generator
from src.channel_manager import channel_manager
from src.database_service import database_manager
from config.settings import settings

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Engine điều phối toàn bộ workflow tạo nội dung YouTube
    Hỗ trợ multi-channel với database riêng biệt
    """
    
    def __init__(self):
        self.config = WorkflowConfig()
        self.active_packages: Dict[str, ContentPackage] = {}
        
    async def create_content_package(self, input_data: InputData) -> ContentPackage:
        """
        Tạo ContentPackage mới và validate channel setup
        """
        try:
            # Nếu không có channel_id, tạo một id tạm thời dựa trên tên kênh
            if not input_data.channel_id:
                channel_name_slug = slugify(input_data.channel_name or "unknown-channel")
                input_data.channel_id = f"ad-hoc-{channel_name_slug}-{uuid.uuid4().hex[:6]}"

            # Validate channel setup
            channel_setup = channel_manager.validate_channel_setup(input_data.channel_id)
            
            if not channel_setup["channel_exists"]:
                raise ValueError(f"Kênh {input_data.channel_id} không tồn tại. Vui lòng tạo kênh trước.")
            
            # Enrich input data với thông tin từ channel config
            enriched_input_data = channel_manager.enrich_input_data(input_data)
            
            # Tạo package ID
            package_id = f"pkg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}"
            
            # Tạo ContentPackage - loại bỏ is_batch_item vì không tồn tại trong model
            package = ContentPackage(
                id=package_id,
                channel_id=input_data.channel_id,
                input_data=enriched_input_data,
                status=ContentStatus.PENDING
            )
            
            package.add_log(f"Tạo package mới cho kênh: {enriched_input_data.channel_name}")
            
            # Lưu vào active packages
            self.active_packages[package_id] = package
            
            logger.info(f"Đã tạo ContentPackage: {package_id} cho kênh {input_data.channel_id}")
            return package
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo ContentPackage: {str(e)}")
            raise
    
    async def _initialize_package(self, input_data: InputData, is_batch: bool = False) -> ContentPackage:
        """
        Khởi tạo một ContentPackage mới mà không cần kiểm tra kênh
        Phù hợp cho cả kênh ad-hoc và kênh quản lý
        """
        # Nếu không có channel_id, tạo một id tạm thời dựa trên tên kênh
        if not input_data.channel_id and input_data.channel_name:
            channel_name_slug = slugify(input_data.channel_name or "unknown-channel")
            input_data.channel_id = f"ad-hoc-{channel_name_slug}-{uuid.uuid4().hex[:6]}"
        
        # Tạo ID package
        package_id = f"pkg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}"
        
        # Tạo ContentPackage - loại bỏ is_batch_item vì không tồn tại trong model
        # Debug: log thông tin input_data trước khi tạo ContentPackage
        logger.info(f"Creating ContentPackage with input_data type: {type(input_data)}")
        logger.info(f"input_data values: channel_id={getattr(input_data, 'channel_id', 'N/A')}, channel_name={getattr(input_data, 'channel_name', 'N/A')}")
        
        # Ensure input_data is properly structured
        if not isinstance(input_data, InputData):
            logger.error(f"input_data is not an InputData instance: {type(input_data)}")
            raise ValueError(f"input_data must be an InputData instance, got {type(input_data)}")
        
        package = ContentPackage(
            id=package_id,
            channel_id=input_data.channel_id,
            input_data=input_data,
            status=ContentStatus.PENDING
        )
        
        # Lưu vào active packages
        self.active_packages[package.id] = package
        logger.info(f"Khởi tạo package mới: {package.id} cho kênh {input_data.channel_id}")
        
        return package
    
    async def run_full_workflow(self, input_data: InputData) -> ContentPackage:
        """
        Chạy toàn bộ workflow tạo nội dung cho một kênh
        """
        package = None
        
        try:
            logger.info(f"=== BẮT ĐẦU WORKFLOW CHO KÊNH: {input_data.channel_id} ===")
            
            # Ad-hoc channels don't need enrichment or validation against ChannelManager
            if input_data.channel_name and input_data.channel_description:
                package = await self._initialize_package(input_data)
                package.log("Bắt đầu workflow cho kênh ad-hoc.")
            else:
                # This is the old flow for managed channels
                enriched_input = channel_manager.enrich_input_data(input_data)
                package = await self._initialize_package(enriched_input)
                package.log(f"Bắt đầu workflow cho kênh quản lý: {package.channel_id}")

            # Giai đoạn 1: Chuẩn bị data
            config = await self._stage_prepare_data(package)
            package.update_status(ContentStatus.GENERATING_CONTENT)

            # Giai đoạn 2: Tạo content
            if self.config.auto_generate_content:
                package = await self._stage_generate_content(package)
            
            # Giai đoạn 3: Tạo hình ảnh
            if self.config.auto_generate_images:
                try:
                    package = await self._stage_generate_images(package)
                except Exception as e:
                    logger.warning(f"[{package.id}] Bỏ qua tạo ảnh do lỗi: {str(e)}")
                    package.add_log(f"⚠️ Bỏ qua tạo ảnh: {str(e)}")
                    # Tiếp tục workflow mà không có ảnh
            
            # Giai đoạn 4: Lưu vào Google Sheets (ưu tiên)
            await self._stage_save_to_database(package)
            
            # 5. Cập nhật trạng thái hoàn thành
            package.status = ContentStatus.GENERATED
            package.add_log("Hoàn thành workflow tạo nội dung")
            
            logger.info(f"=== HOÀN THÀNH WORKFLOW: {package.id} ===")
            return package
            
        except Exception as e:
            error_message = f"Lỗi nghiêm trọng trong workflow: {str(e)}"
            logger.error(error_message, exc_info=True)
            if package:
                package.status = ContentStatus.FAILED
                package.add_log(f"Lỗi: {error_message}")
            
            raise
    
    async def _stage_generate_content(self, package: ContentPackage) -> ContentPackage:
        """
        Giai đoạn 2: Tạo nội dung với AI
        """
        try:
            logger.info(f"[{package.id}] Giai đoạn 2: Tạo nội dung với AI cho kênh {package.channel_id}")
            package.add_log("Bắt đầu tạo nội dung với OpenAI")
            
            # Lấy thông tin kênh để tối ưu hóa content generation
            channel = channel_manager.get_channel(package.channel_id)
            
            # Tạo context đặc biệt cho kênh
            if channel:
                enhanced_context = f"""
Thông tin kênh:
- Tên kênh: {channel.channel_name}
- Phong cách: {channel.content_style or 'Chưa xác định'}
- Đối tượng: {channel.target_audience or 'Chưa xác định'}
- Chủ đề chính: {', '.join(channel.content_topics) if channel.content_topics else 'Đa dạng'}

Yêu cầu tạo nội dung:
{package.input_data.additional_context or ''}
"""
                # Cập nhật context cho input data
                package.input_data.additional_context = enhanced_context
            
            # Đọc và mã hóa ảnh nếu có
            image_base64 = None
            if package.input_data.video_frame_file and os.path.exists(package.input_data.video_frame_file):
                try:
                    with open(package.input_data.video_frame_file, "rb") as image_file:
                        image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
                    package.add_log("Đã mã hóa thành công ảnh tham khảo.")
                    logger.info(f"[{package.id}] Đã đọc và mã hóa ảnh: {package.input_data.video_frame_file}")
                except Exception as e:
                    logger.error(f"[{package.id}] Lỗi khi đọc hoặc mã hóa ảnh: {str(e)}")
                    package.add_log(f"Lỗi đọc ảnh tham khảo: {str(e)}")

            # Tạo nội dung và cải thiện prompts song song
            content, improved_prompts = await ai_generator.generate_parallel_content(
                input_data=package.input_data, 
                image_base64=image_base64
            )
            
            # Cập nhật prompts đã cải thiện
            content.image_prompts = improved_prompts
            
            package.generated_content = content
            package.add_log(f"Đã tạo nội dung: {content.title[:50]}...")
            
            logger.info(f"[{package.id}] Đã tạo nội dung thành công cho kênh {package.channel_id}")
            return package
            
        except Exception as e:
            logger.error(f"[{package.id}] Lỗi giai đoạn tạo nội dung: {str(e)}")
            package.add_log(f"Lỗi tạo nội dung: {str(e)}")
            raise
    
    async def _stage_generate_images(self, package: ContentPackage) -> ContentPackage:
        """
        Giai đoạn 3: Tạo hình ảnh
        """
        try:
            logger.info(f"[{package.id}] Giai đoạn 3: Tạo hình ảnh cho kênh {package.channel_id}")
            package.add_log("Bắt đầu tạo hình ảnh với AI")
            
            if not package.generated_content or not package.generated_content.image_prompts:
                raise ValueError("Không có prompts để tạo ảnh")
            
            # Sử dụng Midjourney với Piapi.ai nếu có API key
            use_midjourney = bool(settings.piapi_api_key)
            logger.info(f"[{package.id}] Piapi API key available: {bool(settings.piapi_api_key)}, using Midjourney: {use_midjourney}")
            
            generated_images = await image_generator.generate_multiple_images(
                prompts=package.generated_content.image_prompts,
                include_thumbnail=True,
                title=package.generated_content.title,
                use_midjourney=use_midjourney
            )
            
            package.generated_images = generated_images
            package.add_log(f"Đã tạo {len(generated_images.additional_images)} ảnh và 1 thumbnail")
            
            logger.info(f"[{package.id}] Đã tạo hình ảnh thành công cho kênh {package.channel_id}")
            return package
            
        except Exception as e:
            logger.error(f"[{package.id}] Lỗi giai đoạn tạo hình ảnh: {str(e)}")
            package.add_log(f"Lỗi tạo hình ảnh: {str(e)}")
            raise
    
    async def _stage_save_to_database(self, package: ContentPackage) -> ContentPackage:
        """
        Giai đoạn 4: Lưu dữ liệu vào Google Sheets (ưu tiên)
        """
        try:
            logger.info(f"[{package.id}] Giai đoạn 4: Lưu dữ liệu vào Google Sheets cho kênh {package.channel_id}")
            package.add_log("Bắt đầu lưu dữ liệu vào Google Sheets")
            
            # Lưu vào database (ưu tiên Google Sheets)
            success = await database_manager.save_content_package(package)
            
            if success:
                package.add_log("✅ Đã lưu thành công vào Google Sheets")
                logger.info(f"[{package.id}] Đã lưu thành công vào database")
            else:
                package.add_log("⚠️ Không thể lưu vào Google Sheets (có thể chưa cấu hình)")
                logger.warning(f"[{package.id}] Không thể lưu vào database")
            
            return package
            
        except Exception as e:
            logger.error(f"[{package.id}] Lỗi giai đoạn lưu database: {str(e)}")
            package.add_log(f"❌ Lỗi lưu database: {str(e)}")
            # Không raise exception để workflow tiếp tục
            return package
    
    async def run_batch_workflow(self, input_data_list: List[InputData]) -> List[ContentPackage]:
        """
        Chạy workflow cho nhiều input data
        """
        results = []
        for input_data in input_data_list:
            try:
                package = await self.run_full_workflow(input_data)
                results.append(package)
            except Exception as e:
                logger.error(f"Lỗi khi xử lý batch item: {str(e)}")
                # Tiếp tục với item tiếp theo
                continue
        
        return results
    
    async def run_channel_batch(self, channel_id: str, input_data_list: List[InputData]) -> List[ContentPackage]:
        """
        Chạy workflow cho nhiều input data của cùng một kênh
        """
        # Đảm bảo tất cả input data đều có channel_id đúng
        for input_data in input_data_list:
            input_data.channel_id = channel_id
        
        return await self.run_batch_workflow(input_data_list)
    
    def get_package_status(self, package_id: str) -> Optional[ContentPackage]:
        """
        Lấy trạng thái của một package
        """
        return self.active_packages.get(package_id)
    
    def get_packages_by_channel(self, channel_id: str) -> List[ContentPackage]:
        """
        Lấy tất cả packages của một kênh
        """
        return [
            package for package in self.active_packages.values()
            if package.channel_id == channel_id
        ]
    
    def get_all_active_packages(self) -> Dict[str, ContentPackage]:
        """
        Lấy tất cả active packages
        """
        return self.active_packages.copy()
    
    def get_channel_statistics(self) -> Dict[str, any]:
        """
        Lấy thống kê theo kênh
        """
        stats = {}
        
        for package in self.active_packages.values():
            channel_id = package.channel_id
            
            if channel_id not in stats:
                stats[channel_id] = {
                    "total": 0,
                    "pending": 0,
                    "processing": 0,
                    "generated": 0,
                    "uploaded": 0,
                    "published": 0,
                    "failed": 0,
                    "channel_name": package.input_data.channel_name
                }
            
            stats[channel_id]["total"] += 1
            
            # Cập nhật counter theo status
            status_key = package.status.value
            if status_key in stats[channel_id]:
                stats[channel_id][status_key] += 1
        
        return stats
    
    async def cleanup_completed_packages(self, max_age_hours: int = 24):
        """
        Xóa các packages đã hoàn thành quá lâu để giảm bộ nhớ
        """
        now = datetime.now()
        packages_to_remove = []
        
        for package_id, package in self.active_packages.items():
            # Chỉ xóa các packages đã hoàn thành hoặc thất bại
            if package.status in [ContentStatus.GENERATED, ContentStatus.PUBLISHED, ContentStatus.FAILED]:
                # Tính thời gian tồn tại
                age = now - package.updated_at
                
                # Nếu quá lâu, đánh dấu để xóa
                if age.total_seconds() > max_age_hours * 3600:
                    packages_to_remove.append(package_id)
        
        # Xóa các packages đã đánh dấu
        for package_id in packages_to_remove:
            del self.active_packages[package_id]
        
        logger.info(f"Đã xóa {len(packages_to_remove)} packages cũ")

    async def _stage_prepare_data(self, package: ContentPackage) -> WorkflowConfig:
        """
        Giai đoạn 1: Chuẩn bị dữ liệu và cấu hình
        Sử dụng trực tiếp thông tin từ InputData nếu có,
        nếu không thì lấy từ ChannelManager.
        """
        package.log("Bắt đầu chuẩn bị dữ liệu")
        
        input_data = package.input_data

        # Tạo config từ thông tin ad-hoc
        if input_data.channel_name and input_data.channel_description:
            channel_config = ChannelConfig(
                channel_id=input_data.channel_id,
                channel_name=input_data.channel_name,
                channel_description=input_data.channel_description
            )
            package.log(f"Sử dụng thông tin kênh ad-hoc: {input_data.channel_name}")
        
        # Nếu không, fallback về lấy config từ channel_manager (luồng cũ)
        else:
            channel_config = channel_manager.get_channel(input_data.channel_id)
            if not channel_config:
                raise ValueError(f"Không tìm thấy cấu hình cho kênh ID: {input_data.channel_id}")
            package.log(f"Lấy thông tin từ kênh đã quản lý: {channel_config.channel_name}")

        config = WorkflowConfig(
            package_id=package.id,
            channel_config=channel_config,
        )
        return config


# Singleton instance
workflow_engine = WorkflowEngine() 