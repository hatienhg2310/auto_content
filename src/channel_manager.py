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
        # Sử dụng trực tiếp channel_mapping_config.json từ root
        self.channels_config_file = "channel_mapping_config.json"
        self.channels: Dict[str, ChannelConfig] = {}
        self._load_channels_config()
    
    def _load_channels_config(self):
        """
        Load cấu hình channels từ channel_mapping_config.json
        """
        try:
            if os.path.exists(self.channels_config_file):
                with open(self.channels_config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Lấy spreadsheet_id chung
                spreadsheet_id = data.get("spreadsheet_id")
                
                # Load channels từ array
                for channel_data in data.get('channels', []):
                    # Bổ sung spreadsheet_id chung cho mỗi channel
                    if spreadsheet_id and not channel_data.get('google_sheets_id'):
                        channel_data['google_sheets_id'] = spreadsheet_id
                    
                    # Parse google_sheet_url để lấy gid nếu có
                    if 'google_sheet_url' in channel_data:
                        import re
                        gid_match = re.search(r'[#&]gid=([0-9]+)', channel_data['google_sheet_url'])
                        if gid_match and not channel_data.get('google_sheet_gid'):
                            channel_data['google_sheet_gid'] = gid_match.group(1)
                    
                    channel = ChannelConfig(**channel_data)
                    self.channels[channel.channel_id] = channel
                
                logger.info(f"Đã load {len(self.channels)} channels từ channel_mapping_config.json")
                
                # Log danh sách channels
                for channel_id, channel in self.channels.items():
                    logger.info(f"  • {channel.channel_name} (ID: {channel_id}) → Sheet: {channel.google_sheet_name}")
                    
            else:
                logger.warning("Không tìm thấy channel_mapping_config.json, tạo cấu hình mặc định")
                self._create_default_config()
                
        except Exception as e:
            logger.error(f"Lỗi khi load channels config: {str(e)}")
            self._create_default_config()
    
    def _create_default_config(self):
        """
        Tạo cấu hình mặc định khi không có file config
        """
        try:
            # Tạo channel mặc định
            default_channel = ChannelConfig(
                channel_id="default_channel",
                channel_name=settings.default_channel_name,
                channel_description=settings.default_channel_description,
                content_style="Giáo dục và giải trí",
                target_audience="Người Việt Nam 18-35 tuổi",
                content_topics=["Technology", "Tutorial", "Review"],
                google_sheets_id=settings.google_sheets_id
            )
            
            self.channels["default_channel"] = default_channel
            logger.info("Đã tạo cấu hình mặc định")
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo cấu hình mặc định: {str(e)}")
    
    def _save_channels_config(self):
        """
        Lưu cấu hình channels vào file channel_mapping_config.json
        """
        try:
            # Chuẩn bị dữ liệu theo format của channel_mapping_config.json
            channels_data = []
            spreadsheet_id = None
            
            for channel in self.channels.values():
                # Lấy spreadsheet_id chung từ channel đầu tiên
                if not spreadsheet_id and channel.google_sheets_id:
                    spreadsheet_id = channel.google_sheets_id
                
                channel_data = {
                    "channel_id": channel.channel_id,
                    "channel_name": channel.channel_name,
                    "channel_description": channel.channel_description,
                    "google_sheet_name": channel.google_sheet_name,
                    "google_sheet_gid": channel.google_sheet_gid,
                    "content_style": channel.content_style,
                    "target_audience": channel.target_audience,
                    "content_topics": channel.content_topics
                }
                
                # Tạo google_sheet_url nếu có đủ thông tin
                if spreadsheet_id and channel.google_sheet_gid:
                    channel_data["google_sheet_url"] = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit?gid={channel.google_sheet_gid}#gid={channel.google_sheet_gid}"
                
                channels_data.append(channel_data)
            
            # Tạo data theo format channel_mapping_config.json
            data = {
                "spreadsheet_id": spreadsheet_id or settings.google_sheets_id,
                "channels": channels_data
            }
            
            # Lưu file
            with open(self.channels_config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info("Đã lưu cấu hình channels vào channel_mapping_config.json")
            
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
                    google_sheet_gid=channel.google_sheet_gid,
                    google_sheet_url=channel.google_sheet_url,
                    airtable_base_id=channel.airtable_base_id,
                    airtable_table_name=channel.airtable_table_name or "Content"
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Lỗi khi lấy channel database config: {str(e)}")
            return None


# Singleton instance
channel_manager = ChannelManager() 