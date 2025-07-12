import json
import os
from typing import Dict, List, Optional
import sys
import pathlib

# Thêm thư mục gốc vào sys.path
root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.models import ChannelConfig, InputData
from config.settings import settings
import logging

logger = logging.getLogger(__name__)


class ChannelManager:
    """
    Quản lý các kênh YouTube và thông tin kênh
    """
    
    def __init__(self):
        self.channels_config_file = os.path.join(settings.data_storage_path, "channels_config.json")
        self.channels: Dict[str, ChannelConfig] = {}
        self._load_channels_config()
    
    def _load_channels_config(self):
        """
        Load cấu hình channels từ file JSON
        """
        try:
            if os.path.exists(self.channels_config_file):
                with open(self.channels_config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load channels
                for channel_data in data.get('channels', []):
                    channel = ChannelConfig(**channel_data)
                    self.channels[channel.channel_id] = channel
                
                logger.info(f"Đã load {len(self.channels)} channels")
            else:
                logger.info("Chưa có file cấu hình channels, tạo cấu hình mặc định")
                self._create_default_config()
                
        except Exception as e:
            logger.error(f"Lỗi khi load channels config: {str(e)}")
            self._create_default_config()
    
    def _create_default_config(self):
        """
        Tạo cấu hình mặc định
        """
        try:
            # Tạo channel mặc định
            default_channel = ChannelConfig(
                channel_id="default_channel",
                channel_name=settings.default_channel_name,
                channel_description=settings.default_channel_description,
                content_style="Giáo dục và giải trí",
                target_audience="Người Việt Nam 18-35 tuổi",
                content_topics=["Technology", "Tutorial", "Review"]
            )
            
            self.channels["default_channel"] = default_channel
            
            self._save_channels_config()
            logger.info("Đã tạo cấu hình mặc định")
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo cấu hình mặc định: {str(e)}")
    
    def _save_channels_config(self):
        """
        Lưu cấu hình channels vào file
        """
        try:
            # Đảm bảo thư mục tồn tại
            os.makedirs(os.path.dirname(self.channels_config_file), exist_ok=True)
            
            # Chuẩn bị dữ liệu
            data = {
                "channels": [channel.dict() for channel in self.channels.values()]
            }
            
            # Lưu file
            with open(self.channels_config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info("Đã lưu cấu hình channels")
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu channels config: {str(e)}")
    
    def add_channel(self, channel_config: ChannelConfig) -> bool:
        """
        Thêm kênh mới
        """
        try:
            self.channels[channel_config.channel_id] = channel_config
            
            self._save_channels_config()
            logger.info(f"Đã thêm kênh: {channel_config.channel_name}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi thêm kênh: {str(e)}")
            return False
    
    def update_channel(self, channel_id: str, channel_config: ChannelConfig) -> bool:
        """
        Cập nhật kênh
        """
        try:
            if channel_id in self.channels:
                self.channels[channel_id] = channel_config
                self._save_channels_config()
                logger.info(f"Đã cập nhật kênh: {channel_config.channel_name}")
                return True
            else:
                logger.warning(f"Không tìm thấy kênh: {channel_id}")
                return False
                
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật kênh: {str(e)}")
            return False
    
    def remove_channel(self, channel_id: str) -> bool:
        """
        Xóa kênh
        """
        try:
            if channel_id in self.channels:
                del self.channels[channel_id]
                
                self._save_channels_config()
                logger.info(f"Đã xóa kênh: {channel_id}")
                return True
            else:
                logger.warning(f"Không tìm thấy kênh: {channel_id}")
                return False
                
        except Exception as e:
            logger.error(f"Lỗi khi xóa kênh: {str(e)}")
            return False
    
    def get_channel(self, channel_id: str) -> Optional[ChannelConfig]:
        """
        Lấy thông tin kênh
        """
        return self.channels.get(channel_id)
    
    def get_all_channels(self) -> Dict[str, ChannelConfig]:
        """
        Lấy tất cả kênh
        """
        return self.channels.copy()
    
    def get_active_channels(self) -> List[ChannelConfig]:
        """
        Lấy các kênh đang hoạt động
        """
        return [channel for channel in self.channels.values() if channel.is_active]
    
    def enrich_input_data(self, input_data: InputData) -> InputData:
        """
        Bổ sung thông tin cho InputData từ ChannelConfig
        """
        try:
            channel = self.get_channel(input_data.channel_id)
            
            if channel:
                # Auto-fill thông tin từ channel config
                input_data.channel_name = channel.channel_name
                input_data.channel_description = channel.channel_description
                
                # Nếu không có context, dùng thông tin từ channel
                if not input_data.additional_context and channel.content_style:
                    input_data.additional_context = f"Phong cách: {channel.content_style}. Đối tượng: {channel.target_audience}"
                
                logger.info(f"Đã enrich input data cho kênh: {channel.channel_name}")
            else:
                logger.warning(f"Không tìm thấy kênh: {input_data.channel_id}")
            
            return input_data
            
        except Exception as e:
            logger.error(f"Lỗi khi enrich input data: {str(e)}")
            return input_data
    
    def validate_channel_setup(self, channel_id: str) -> Dict[str, bool]:
        """
        Kiểm tra setup của kênh
        """
        result = {
            "channel_exists": False
        }
        
        try:
            # Kiểm tra channel exists
            channel = self.get_channel(channel_id)
            if channel:
                result["channel_exists"] = True
            
        except Exception as e:
            logger.error(f"Lỗi khi validate channel setup: {str(e)}")
        
        return result


    def get_channel_database(self, channel_id: str) -> Optional['ChannelDatabase']:
        """
        Lấy cấu hình database cho kênh
        """
        try:
            from src.models import ChannelDatabase
            channel = self.get_channel(channel_id)
            
            if channel:
                return ChannelDatabase(
                    channel_id=channel_id,
                    google_sheets_id=channel.google_sheets_id,
                    google_sheet_name=channel.google_sheet_name,
                    airtable_base_id=channel.airtable_base_id,
                    airtable_table_name=channel.airtable_table_name or "Content"
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Lỗi khi lấy channel database config: {str(e)}")
            return None


# Singleton instance
channel_manager = ChannelManager() 