#!/usr/bin/env python3
"""
Script để setup các kênh YouTube từ file cấu hình
"""

import json
import sys
import os
from pathlib import Path

# Thêm thư mục src vào path
src_dir = Path(__file__).parent / "src"
sys.path.append(str(src_dir))

from src.models import ChannelConfig
from src.channel_manager import channel_manager
from config.settings import settings


def load_channel_config():
    """Load cấu hình từ file JSON"""
    config_file = "channel_mapping_config.json"
    
    if not os.path.exists(config_file):
        print(f"❌ Không tìm thấy file {config_file}")
        return None
    
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def setup_channels():
    """Setup tất cả các kênh"""
    print("🚀 Bắt đầu setup các kênh YouTube...")
    
    # Load config
    config = load_channel_config()
    if not config:
        return False
    
    # Cập nhật Google Sheets ID trong settings
    spreadsheet_id = config.get("spreadsheet_id")
    if spreadsheet_id:
        print(f"📊 Sử dụng Google Sheets: {spreadsheet_id}")
        # Cập nhật settings (có thể cần update .env file)
        settings.google_sheets_id = spreadsheet_id
    
    # Setup từng kênh
    channels_data = config.get("channels", [])
    success_count = 0
    
    for channel_data in channels_data:
        try:
            # Tạo ChannelConfig
            channel_config = ChannelConfig(
                channel_id=channel_data["channel_id"],
                channel_name=channel_data["channel_name"],
                channel_description=channel_data["channel_description"],
                google_sheets_id=spreadsheet_id,  # Cùng một spreadsheet
                google_sheet_name=channel_data["google_sheet_name"],  # Khác sheet name
                content_style=channel_data.get("content_style"),
                target_audience=channel_data.get("target_audience"),
                content_topics=channel_data.get("content_topics", [])
            )
            
            # Thêm vào channel manager
            success = channel_manager.add_channel(channel_config)
            
            if success:
                print(f"✅ Đã setup kênh: {channel_config.channel_name} → Sheet: {channel_data['google_sheet_name']}")
                success_count += 1
            else:
                print(f"❌ Lỗi setup kênh: {channel_config.channel_name}")
                
        except Exception as e:
            print(f"❌ Lỗi khi setup kênh {channel_data.get('channel_name', 'Unknown')}: {str(e)}")
    
    print(f"\n🎯 Đã setup thành công {success_count}/{len(channels_data)} kênh")
    
    # Hiển thị danh sách kênh
    print("\n📋 Danh sách kênh đã setup:")
    all_channels = channel_manager.get_all_channels()
    for channel_id, channel in all_channels.items():
        sheet_name = getattr(channel, 'google_sheet_name', 'Sheet mặc định')
        print(f"   • {channel.channel_name} (ID: {channel_id}) → {sheet_name}")
    
    return success_count > 0


if __name__ == "__main__":
    print("=" * 60)
    print("🎵 YOUTUBE CONTENT AUTOMATION - CHANNEL SETUP")
    print("=" * 60)
    
    success = setup_channels()
    
    if success:
        print("\n✅ Setup hoàn tất! Bạn có thể chạy server:")
        print("   python src/main.py")
        print("\n💡 Mỗi kênh sẽ tự động ghi dữ liệu vào sheet riêng biệt trong cùng một Google Spreadsheet.")
    else:
        print("\n❌ Setup thất bại. Vui lòng kiểm tra lại cấu hình.")
        sys.exit(1) 