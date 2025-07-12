import gspread
from google.oauth2.service_account import Credentials
from airtable import Airtable
import pandas as pd
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import os

from src.models import ContentPackage, DatabaseRecord, GeneratedContent, GeneratedImages, ChannelDatabase
from config.settings import settings
import logging
from src.channel_manager import channel_manager

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """
    Dịch vụ quản lý Google Sheets
    """
    
    def __init__(self):
        self.credentials_file = settings.google_credentials_file
        self.sheets_id = settings.google_sheets_id
        self.client = None
        self.worksheet = None
        
    async def initialize(self):
        """Khởi tạo kết nối Google Sheets"""
        try:
            # Nếu không có credentials file, chỉ cảnh báo và bỏ qua
            if not self.credentials_file or not os.path.exists(self.credentials_file):
                logger.warning("Không tìm thấy Google credentials file. Google Sheets sẽ bị vô hiệu hóa.")
                self.client = None
                self.worksheet = None
                return
            # Định nghĩa scope cho Google Sheets API
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            # Tạo credentials
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=scope
            )
            # Tạo client
            self.client = gspread.authorize(creds)
            # Mở spreadsheet
            spreadsheet = self.client.open_by_key(self.sheets_id)
            # Sử dụng worksheet đầu tiên hoặc tạo mới
            try:
                self.worksheet = spreadsheet.worksheet("YouTube_Content")
            except gspread.WorksheetNotFound:
                self.worksheet = spreadsheet.add_worksheet(
                    title="YouTube_Content", 
                    rows="1000", 
                    cols="12"
                )
                # Thêm header
                headers = [
                    "Package ID", "Channel Name", "Video Title", "Thumbnail Name",
                    "Video Description", "Video Tags", "Thumbnail Image URL",
                    "Video URL", "Status", "Created By", "Created At", "Updated At"
                ]
                self.worksheet.append_row(headers)
            logger.info("Đã khởi tạo kết nối Google Sheets thành công")
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo Google Sheets: {str(e)}")
            self.client = None
            self.worksheet = None
            # Không raise nữa
            return
    
    async def save_record(self, record: DatabaseRecord) -> bool:
        """Lưu record vào Google Sheets"""
        try:
            if not self.worksheet:
                await self.initialize()
            if not self.worksheet:
                logger.warning("Google Sheets chưa được cấu hình hoặc không khả dụng. Bỏ qua lưu dữ liệu.")
                return False
            # Chuẩn bị dữ liệu
            row_data = [
                record.package_id,
                record.channel_name,
                record.video_title,
                record.thumbnail_name,
                record.video_description,
                record.video_tags,
                record.thumbnail_image_url,
                record.video_url or "",
                record.status,
                record.created_by,
                record.created_at,
                record.updated_at
            ]
            # Thêm row vào sheet
            await asyncio.to_thread(self.worksheet.append_row, row_data)
            logger.info(f"Đã lưu record vào Google Sheets: {record.package_id}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu vào Google Sheets: {str(e)}")
            return False
    
    async def update_record(self, package_id: str, updates: Dict[str, Any]) -> bool:
        """Cập nhật record trong Google Sheets"""
        try:
            if not self.worksheet:
                await self.initialize()
            if not self.worksheet:
                logger.warning("Google Sheets chưa được cấu hình hoặc không khả dụng. Bỏ qua cập nhật dữ liệu.")
                return False
            # Tìm row có package_id tương ứng
            all_records = await asyncio.to_thread(self.worksheet.get_all_records)
            for i, record in enumerate(all_records, start=2):  # Start=2 vì row 1 là header
                if record.get("Package ID") == package_id:
                    # Cập nhật các field
                    for field, value in updates.items():
                        col_map = {
                            "video_url": "H",  # Video URL column
                            "status": "I",     # Status column
                            "updated_at": "L"  # Updated At column
                        }
                        if field in col_map:
                            cell = f"{col_map[field]}{i}"
                            await asyncio.to_thread(self.worksheet.update, cell, value)
                    logger.info(f"Đã cập nhật record trong Google Sheets: {package_id}")
                    return True
            logger.warning(f"Không tìm thấy record để cập nhật: {package_id}")
            return False
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Google Sheets: {str(e)}")
            return False
    
    async def get_all_records(self) -> List[Dict[str, Any]]:
        """Lấy tất cả records từ Google Sheets"""
        try:
            if not self.worksheet:
                await self.initialize()
            if not self.worksheet:
                logger.warning("Google Sheets chưa được cấu hình hoặc không khả dụng. Trả về danh sách rỗng.")
                return []
            records = await asyncio.to_thread(self.worksheet.get_all_records)
            return records
        except Exception as e:
            logger.error(f"Lỗi khi lấy records từ Google Sheets: {str(e)}")
            return []


class AirtableService:
    """
    Dịch vụ quản lý Airtable
    """
    
    def __init__(self):
        self.api_key = settings.airtable_api_key
        self.base_id = settings.airtable_base_id
        self.table_name = settings.airtable_table_name
        self.airtable = None
        
    def initialize(self):
        """Khởi tạo kết nối Airtable"""
        try:
            self.airtable = Airtable(self.base_id, self.table_name, self.api_key)
            logger.info("Đã khởi tạo kết nối Airtable thành công")
            
        except Exception as e:
            logger.error(f"Lỗi khi khởi tạo Airtable: {str(e)}")
            raise
    
    async def save_record(self, record: DatabaseRecord) -> Optional[str]:
        """Lưu record vào Airtable"""
        try:
            if not self.airtable:
                self.initialize()
            
            # Chuẩn bị dữ liệu cho Airtable
            airtable_data = {
                "Package ID": record.package_id,
                "Channel Name": record.channel_name,
                "Video Title": record.video_title,
                "Thumbnail Name": record.thumbnail_name,
                "Video Description": record.video_description,
                "Video Tags": record.video_tags,
                "Thumbnail Image URL": record.thumbnail_image_url,
                "Video URL": record.video_url or "",
                "Status": record.status,
                "Created By": record.created_by,
                "Created At": record.created_at,
                "Updated At": record.updated_at
            }
            
            # Tạo record trong Airtable
            result = await asyncio.to_thread(self.airtable.insert, airtable_data)
            
            logger.info(f"Đã lưu record vào Airtable: {record.package_id}")
            return result.get("id")
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu vào Airtable: {str(e)}")
            return None
    
    async def update_record(self, airtable_record_id: str, updates: Dict[str, Any]) -> bool:
        """Cập nhật record trong Airtable"""
        try:
            if not self.airtable:
                self.initialize()
            
            # Chuẩn bị dữ liệu cập nhật
            update_data = {}
            field_mapping = {
                "video_url": "Video URL",
                "status": "Status",
                "updated_at": "Updated At"
            }
            
            for field, value in updates.items():
                if field in field_mapping:
                    update_data[field_mapping[field]] = value
            
            # Cập nhật record
            await asyncio.to_thread(self.airtable.update, airtable_record_id, update_data)
            
            logger.info(f"Đã cập nhật record trong Airtable: {airtable_record_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Airtable: {str(e)}")
            return False
    
    async def find_record_by_package_id(self, package_id: str) -> Optional[Dict[str, Any]]:
        """Tìm record theo package ID"""
        try:
            if not self.airtable:
                self.initialize()
            
            # Tìm kiếm record
            formula = f"{{Package ID}} = '{package_id}'"
            records = await asyncio.to_thread(
                self.airtable.get_all, 
                formula=formula
            )
            
            if records:
                return records[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Lỗi khi tìm record trong Airtable: {str(e)}")
            return None
    
    async def sync_from_sheets(self, sheets_records: List[Dict[str, Any]]) -> int:
        """Đồng bộ dữ liệu từ Google Sheets sang Airtable"""
        try:
            if not self.airtable:
                self.initialize()
            
            synced_count = 0
            
            for sheets_record in sheets_records:
                package_id = sheets_record.get("Package ID")
                if not package_id:
                    continue
                
                # Kiểm tra xem record đã tồn tại trong Airtable chưa
                existing_record = await self.find_record_by_package_id(package_id)
                
                if not existing_record:
                    # Tạo DatabaseRecord từ sheets_record
                    db_record = DatabaseRecord(
                        package_id=package_id,
                        channel_name=sheets_record.get("Channel Name", ""),
                        video_title=sheets_record.get("Video Title", ""),
                        thumbnail_name=sheets_record.get("Thumbnail Name", ""),
                        video_description=sheets_record.get("Video Description", ""),
                        video_tags=sheets_record.get("Video Tags", ""),
                        thumbnail_image_url=sheets_record.get("Thumbnail Image URL", ""),
                        video_url=sheets_record.get("Video URL", ""),
                        status=sheets_record.get("Status", ""),
                        created_by=sheets_record.get("Created By", ""),
                        created_at=sheets_record.get("Created At", ""),
                        updated_at=sheets_record.get("Updated At", "")
                    )
                    
                    # Lưu vào Airtable
                    airtable_id = await self.save_record(db_record)
                    if airtable_id:
                        synced_count += 1
            
            logger.info(f"Đã đồng bộ {synced_count} records từ Sheets sang Airtable")
            return synced_count
            
        except Exception as e:
            logger.error(f"Lỗi khi đồng bộ từ Sheets: {str(e)}")
            return 0


class DatabaseManager:
    """
    Quản lý kết nối và thao tác với databases (Google Sheets + Airtable)
    Hỗ trợ multi-channel với database riêng biệt
    """
    
    def __init__(self):
        self.google_client = None
        self.airtable_clients: Dict[str, Airtable] = {}  # channel_id -> Airtable client
        self._setup_google_sheets()
    
    def _setup_google_sheets(self):
        """
        Thiết lập kết nối Google Sheets
        """
        try:
            if settings.google_credentials_file and os.path.exists(settings.google_credentials_file):
                scope = [
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/drive'
                ]
                
                creds = Credentials.from_service_account_file(
                    settings.google_credentials_file, 
                    scopes=scope
                )
                
                self.google_client = gspread.authorize(creds)
                logger.info("Đã kết nối Google Sheets thành công")
            else:
                logger.warning("Không tìm thấy Google credentials file")
                
        except Exception as e:
            logger.error(f"Lỗi khi setup Google Sheets: {str(e)}")
    
    def _get_airtable_client(self, channel_id: str) -> Optional[Airtable]:
        """
        Lấy Airtable client cho kênh cụ thể
        """
        try:
            # Kiểm tra cache
            if channel_id in self.airtable_clients:
                return self.airtable_clients[channel_id]
            
            # Lấy cấu hình database cho kênh
            db_config = channel_manager.get_channel_database(channel_id)
            
            if not db_config or not db_config.airtable_base_id:
                logger.warning(f"Không có cấu hình Airtable cho kênh: {channel_id}")
                return None
            
            if not settings.airtable_api_key:
                logger.warning("Không có Airtable API key")
                return None
            
            # Tạo client mới
            client = Airtable(
                base_id=db_config.airtable_base_id,
                table_name=db_config.airtable_table_name,
                api_key=settings.airtable_api_key
            )
            
            # Cache client
            self.airtable_clients[channel_id] = client
            logger.info(f"Đã tạo Airtable client cho kênh: {channel_id}")
            
            return client
            
        except Exception as e:
            logger.error(f"Lỗi khi tạo Airtable client cho kênh {channel_id}: {str(e)}")
            return None
    
    def _get_google_sheet(self, channel_id: str):
        """
        Lấy Google Sheet cho kênh cụ thể - hỗ trợ URL với GID và multi-sheet
        """
        try:
            if not self.google_client:
                return None
            
            # Lấy cấu hình database cho kênh
            db_config = channel_manager.get_channel_database(channel_id)
            logger.info(f"Debug - Channel ID: {channel_id}, DB Config: {db_config}")
            
            # Parse Google Sheet URL hoặc sử dụng ID trực tiếp
            if db_config:
                if hasattr(db_config, 'google_sheet_url') and db_config.google_sheet_url:
                    # Parse từ URL để lấy sheets_id và gid
                    sheet_id, gid = db_config.parse_google_sheet_url()
                    logger.info(f"✅ Parse từ URL - Sheets ID: {sheet_id}, GID: {gid}")
                else:
                    # Sử dụng config truyền thống
                    sheet_id = db_config.google_sheets_id
                    gid = getattr(db_config, 'google_sheet_gid', None)
                    logger.info(f"Sử dụng config truyền thống - Sheets ID: {sheet_id}, GID: {gid}")
            else:
                # Fallback về settings mặc định
                sheet_id = settings.google_sheets_id
                gid = None
                logger.info(f"Sử dụng Google Sheets ID mặc định: {sheet_id}")
            
            if not sheet_id:
                logger.warning(f"Không có Google Sheets ID cho kênh: {channel_id}")
                return None
            
            # Mở spreadsheet
            spreadsheet = self.google_client.open_by_key(sheet_id)
            
            # Xác định worksheet theo ưu tiên: GID > Sheet Name > Default
            worksheet = None
            
            if gid:
                # Ưu tiên sử dụng GID để mở sheet cụ thể
                try:
                    # Tìm worksheet theo GID
                    for ws in spreadsheet.worksheets():
                        if str(ws.id) == str(gid):
                            worksheet = ws
                            logger.info(f"✅ Đã mở sheet theo GID '{gid}' ('{ws.title}') cho kênh {channel_id}")
                            break
                    
                    if not worksheet:
                        logger.warning(f"Không tìm thấy sheet với GID '{gid}', fallback về sheet name")
                except Exception as e:
                    logger.warning(f"Lỗi khi mở sheet theo GID '{gid}': {str(e)}")
            
            # Fallback về sheet name nếu không có GID hoặc GID không tìm thấy
            if not worksheet and db_config and db_config.google_sheet_name:
                sheet_name = db_config.google_sheet_name
                logger.info(f"Tìm sheet name từ config: '{sheet_name}' cho kênh {channel_id}")
                try:
                    worksheet = spreadsheet.worksheet(sheet_name)
                    logger.info(f"✅ Đã mở sheet '{sheet_name}' cho kênh {channel_id}")
                except Exception as e:
                    logger.warning(f"Không tìm thấy sheet '{sheet_name}', tạo mới... Error: {str(e)}")
                    # Tạo sheet mới nếu không tồn tại
                    worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="10")
                    logger.info(f"✅ Đã tạo sheet mới '{sheet_name}' cho kênh {channel_id}")
            
            # Fallback cuối cùng về sheet đầu tiên
            if not worksheet:
                logger.warning(f"Không có sheet name trong config cho kênh {channel_id}, sử dụng sheet mặc định")
                worksheet = spreadsheet.sheet1
                logger.info(f"Sử dụng sheet mặc định cho kênh {channel_id}")
            
            return worksheet
            
        except Exception as e:
            logger.error(f"Lỗi khi mở Google Sheet cho kênh {channel_id}: {str(e)}")
            return None
    
    def _package_to_record(self, package: ContentPackage) -> DatabaseRecord:
        """
        Chuyển ContentPackage thành DatabaseRecord
        """
        # Lấy URL ảnh - ưu tiên Midjourney URLs (4 URLs phân cách bằng |)
        thumbnail_image_url = ""
        if package.generated_images:
            if package.generated_images.midjourney_urls:
                # Sử dụng phương thức get_display_urls để lấy chuỗi URLs
                thumbnail_image_url = package.generated_images.get_display_urls()
            elif package.generated_images.thumbnail_url:
                # Fallback về thumbnail_url đơn lẻ
                thumbnail_image_url = package.generated_images.thumbnail_url
        
        # Clean tags before saving to database (ensure single-word format)
        cleaned_tags = []
        if package.generated_content and package.generated_content.tags:
            for tag in package.generated_content.tags:
                if tag and isinstance(tag, str):
                    # Remove any remaining spaces, punctuation, and convert to single word
                    clean_tag = tag.strip().lower()
                    clean_tag = clean_tag.replace(" ", "").replace("-", "").replace(".", "").replace(",", "")
                    clean_tag = clean_tag.replace("!", "").replace("?", "").replace(";", "").replace(":", "")
                    if clean_tag and len(clean_tag) > 1:
                        cleaned_tags.append(clean_tag)
        
        return DatabaseRecord(
            package_id=package.id,
            channel_id=package.channel_id,
            channel_name=package.input_data.channel_name or "Unknown Channel",
            video_title=package.generated_content.title if package.generated_content else "No Title",
            thumbnail_name=package.generated_content.thumbnail_name if package.generated_content else "No Thumbnail",
            video_description=package.generated_content.description if package.generated_content else "No Description",
            video_tags=", ".join(cleaned_tags),
            thumbnail_image_url=thumbnail_image_url,
            video_url=package.youtube_data.video_url if package.youtube_data else "",
            status=package.status.value,
            created_by=package.input_data.created_by,
            created_at=package.created_at.isoformat(),
            updated_at=package.updated_at.isoformat()
        )
    
    async def save_content_package(self, package: ContentPackage) -> bool:
        """
        Lưu ContentPackage vào database (cả Google Sheets và Airtable tương ứng với kênh)
        """
        try:
            logger.info(f"Lưu package {package.id} cho kênh {package.channel_id}")
            
            # Chuyển package thành record
            record = self._package_to_record(package)
            
            # Lưu vào Google Sheets
            google_success = await self._save_to_google_sheets(package.channel_id, record)
            
            # Lưu vào Airtable của kênh tương ứng
            airtable_success = await self._save_to_airtable(package.channel_id, record)
            
            # Thành công nếu ít nhất 1 database lưu được
            success = google_success or airtable_success
            
            if success:
                logger.info(f"Đã lưu package {package.id} thành công")
            else:
                logger.error(f"Lỗi khi lưu package {package.id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu content package: {str(e)}")
            return False
    
    async def _save_to_google_sheets_custom_format(self, channel_id: str, record: DatabaseRecord) -> bool:
        """
        Lưu record vào Google Sheets với format tùy chỉnh của user
        Cấu trúc: STT | Ảnh gen title | Title Video | Tên Thumb | Description | Tags | Ảnh Thumb
        """
        try:
            worksheet = self._get_google_sheet(channel_id)
            
            if not worksheet:
                return False
            
            # Kiểm tra header có tồn tại không - tìm header thực tế thay vì chỉ row 1
            all_values = worksheet.get_all_values()
            header_found = False
            header_row_index = -1
            
            # Tìm header thực tế (có chứa "STT" và "Title Video")
            for i, row in enumerate(all_values):
                if len(row) >= 3 and "STT" in str(row[0]) and "Title Video" in str(row[2]):
                    header_found = True
                    header_row_index = i
                    logger.info(f"📋 Found existing header at row {i+1}: {row[:3]}")
                    break
            
            if not header_found:
                # Chỉ tạo header mới nếu thực sự không có, và KHÔNG clear dữ liệu
                logger.info("📋 No proper header found, adding header to existing data")
                headers = [
                    "STT", "Ảnh gen title", "Title Video", "Tên Thumb", 
                    "Description", "Tags", "Ảnh Thumb"
                ]
                # Insert header ở đầu nếu sheet trống, hoặc tìm vị trí phù hợp
                if len(all_values) == 0:
                    worksheet.append_row(headers)
                else:
                    # Tìm vị trí trống để insert header
                    insert_pos = 1
                    for i, row in enumerate(all_values):
                        if not any(cell.strip() for cell in row if cell):  # Row trống
                            insert_pos = i + 1
                            break
                    worksheet.insert_row(headers, insert_pos)
                    logger.info(f"📋 Inserted header at row {insert_pos}")
            else:
                logger.info(f"📋 Using existing header at row {header_row_index + 1}")
            
            # Tính STT (số thứ tự) dựa trên dữ liệu hiện có (sử dụng all_values đã load)
            stt = self._calculate_next_stt_from_values(all_values)
            
            # Log thông tin worksheet để debug
            worksheet_title = worksheet.title
            worksheet_id = worksheet.id
            logger.info(f"📊 Saving to worksheet: '{worksheet_title}' (ID: {worksheet_id}, GID: {worksheet_id}) for channel: {channel_id}")
            
            # Tạo dữ liệu theo format của user
            row_data = [
                stt,                                                    # A: STT
                record.thumbnail_image_url or "",                       # B: Ảnh gen title (tạm dùng thumbnail URL)
                record.video_title,                                     # C: Title Video
                record.thumbnail_name,                                  # D: Tên Thumb  
                record.video_description[:1000],                       # E: Description (giới hạn 1000 ký tự)
                record.video_tags,                                      # F: Tags
                record.thumbnail_image_url or ""                        # G: Ảnh Thumb
            ]
            
            logger.info(f"📝 Appending row with STT={stt}, Title='{record.video_title[:50]}...' to sheet '{worksheet_title}'")
            
            # Debug: Current state
            logger.info(f"🔍 Current sheet state: {len(all_values)} rows, last row: {all_values[-1][:3] if all_values else 'EMPTY'}")
            
            # Thay vì append_row, dùng insert vào vị trí cụ thể để tránh confusion do multiple headers
            current_rows = len(all_values)
            target_row = current_rows + 1
            
            logger.info(f"📍 Inserting at specific row {target_row} to avoid header confusion")
            logger.info(f"🎯 Row data to insert: {row_data[:3]}...")
            
            # Insert vào row cụ thể
            try:
                await asyncio.to_thread(
                    worksheet.insert_row, 
                    row_data, 
                    target_row
                )
                logger.info(f"✅ insert_row completed successfully")
                
                # Verify result (refresh data)
                all_values_after = worksheet.get_all_values() 
                logger.info(f"🔍 AFTER insert: {len(all_values_after)} rows (was {current_rows})")
                if len(all_values_after) > current_rows:
                    logger.info(f"✅ Row count increased! Last row: {all_values_after[-1][:3]}")
                else:
                    logger.error(f"❌ Row count did NOT increase! Possible conflict or error.")
                    # Log all rows for debugging
                    for i, row in enumerate(all_values_after[-5:], len(all_values_after)-4):
                        logger.error(f"   Row {i}: {row[:3]}")
                    
            except Exception as insert_error:
                logger.error(f"❌ insert_row failed: {insert_error}")
                raise insert_error
            
            logger.info(f"✅ Successfully saved to Google Sheets (custom format) for channel {channel_id} in sheet '{worksheet_title}' at row {target_row}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu vào Google Sheets (custom format) cho kênh {channel_id}: {str(e)}")
            return False

    async def _save_to_google_sheets(self, channel_id: str, record: DatabaseRecord) -> bool:
        """
        Lưu record vào Google Sheets - sử dụng format tùy chỉnh của user
        """
        # Ưu tiên sử dụng format tùy chỉnh
        return await self._save_to_google_sheets_custom_format(channel_id, record)
    
    async def _save_to_airtable(self, channel_id: str, record: DatabaseRecord) -> bool:
        """
        Lưu record vào Airtable của kênh
        """
        try:
            airtable_client = self._get_airtable_client(channel_id)
            
            if not airtable_client:
                return False
            
            # Chuẩn bị data cho Airtable
            airtable_data = {
                "Package ID": record.package_id,
                "Channel ID": record.channel_id,
                "Channel Name": record.channel_name,
                "Video Title": record.video_title,
                "Thumbnail Name": record.thumbnail_name,
                "Video Description": record.video_description[:1000],  # Airtable limit
                "Video Tags": record.video_tags,
                "Thumbnail Image URL": record.thumbnail_image_url,
                "Video URL": record.video_url or "",
                "Status": record.status,
                "Created By": record.created_by,
                "Created At": record.created_at,
                "Updated At": record.updated_at
            }
            
            # Insert vào Airtable
            await asyncio.to_thread(airtable_client.insert, airtable_data)
            logger.info(f"Đã lưu vào Airtable cho kênh {channel_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi lưu vào Airtable cho kênh {channel_id}: {str(e)}")
            return False
    
    async def update_content_package(self, package: ContentPackage) -> bool:
        """
        Cập nhật ContentPackage trong database
        """
        try:
            logger.info(f"Cập nhật package {package.id} cho kênh {package.channel_id}")
            
            # Chuyển package thành record
            record = self._package_to_record(package)
            
            # Cập nhật trong cả 2 databases
            google_success = await self._update_in_google_sheets(package.channel_id, record)
            airtable_success = await self._update_in_airtable(package.channel_id, record)
            
            success = google_success or airtable_success
            
            if success:
                logger.info(f"Đã cập nhật package {package.id} thành công")
            
            return success
            
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật content package: {str(e)}")
            return False
    
    async def _update_in_google_sheets(self, channel_id: str, record: DatabaseRecord) -> bool:
        """
        Cập nhật record trong Google Sheets với format tùy chỉnh
        """
        try:
            worksheet = self._get_google_sheet(channel_id)
            
            if not worksheet:
                return False
            
            # Với format tùy chỉnh, cột C (Title Video) là unique identifier
            all_values = worksheet.get_all_values()
            
            for i, row in enumerate(all_values):
                if i == 0:  # Skip header
                    continue
                if len(row) > 2 and row[2] == record.video_title:  # Cột C là Title Video
                    row_num = i + 1
                    
                    # Cập nhật row theo format tùy chỉnh
                    row_data = [
                        row[0],                                 # A: Giữ nguyên STT
                        record.thumbnail_image_url or "",       # B: Ảnh gen title
                        record.video_title,                     # C: Title Video
                        record.thumbnail_name,                  # D: Tên Thumb
                        record.video_description[:1000],       # E: Description
                        record.video_tags,                      # F: Tags
                        record.thumbnail_image_url or ""        # G: Ảnh Thumb
                    ]
                    
                    await asyncio.to_thread(worksheet.update, f"A{row_num}:G{row_num}", [row_data])
                    logger.info(f"Đã cập nhật Google Sheets cho title: {record.video_title}")
                    return True
            
            # Nếu không tìm thấy, tạo mới
            return await self._save_to_google_sheets(channel_id, record)
            
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Google Sheets: {str(e)}")
            return False
    
    async def _update_in_airtable(self, channel_id: str, record: DatabaseRecord) -> bool:
        """
        Cập nhật record trong Airtable
        """
        try:
            airtable_client = self._get_airtable_client(channel_id)
            
            if not airtable_client:
                return False
            
            # Tìm record theo Package ID
            records = await asyncio.to_thread(
                airtable_client.get_all,
                formula=f"{{Package ID}} = '{record.package_id}'"
            )
            
            # Chuẩn bị data
            airtable_data = {
                "Package ID": record.package_id,
                "Channel ID": record.channel_id,
                "Channel Name": record.channel_name,
                "Video Title": record.video_title,
                "Thumbnail Name": record.thumbnail_name,
                "Video Description": record.video_description[:1000],
                "Video Tags": record.video_tags,
                "Thumbnail Image URL": record.thumbnail_image_url,
                "Video URL": record.video_url or "",
                "Status": record.status,
                "Created By": record.created_by,
                "Created At": record.created_at,
                "Updated At": record.updated_at
            }
            
            if records:
                # Update existing record
                record_id = records[0]['id']
                await asyncio.to_thread(airtable_client.update, record_id, airtable_data)
                logger.info(f"Đã cập nhật Airtable record cho package {record.package_id}")
            else:
                # Create new record
                await asyncio.to_thread(airtable_client.insert, airtable_data)
                logger.info(f"Đã tạo mới Airtable record cho package {record.package_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật Airtable: {str(e)}")
            return False
    
    async def sync_databases(self) -> bool:
        """
        Đồng bộ dữ liệu giữa Google Sheets và Airtable cho tất cả các kênh
        """
        try:
            logger.info("Bắt đầu đồng bộ databases cho tất cả kênh")
            
            all_channels = channel_manager.get_all_channels()
            sync_results = []
            
            for channel_id in all_channels.keys():
                try:
                    result = await self._sync_channel_databases(channel_id)
                    sync_results.append(result)
                    logger.info(f"Đồng bộ kênh {channel_id}: {'thành công' if result else 'thất bại'}")
                except Exception as e:
                    logger.error(f"Lỗi khi đồng bộ kênh {channel_id}: {str(e)}")
                    sync_results.append(False)
            
            # Thành công nếu ít nhất 1 kênh đồng bộ được
            overall_success = any(sync_results)
            
            logger.info(f"Hoàn thành đồng bộ: {sum(sync_results)}/{len(sync_results)} kênh thành công")
            return overall_success
            
        except Exception as e:
            logger.error(f"Lỗi khi đồng bộ databases: {str(e)}")
            return False
    
    async def _sync_channel_databases(self, channel_id: str) -> bool:
        """
        Đồng bộ database cho một kênh cụ thể
        """
        try:
            # Kiểm tra cấu hình
            db_config = channel_manager.get_channel_database(channel_id)
            if not db_config:
                logger.warning(f"Không có cấu hình database cho kênh {channel_id}")
                return False
            
            # TODO: Implement sync logic tùy theo nhu cầu
            # Có thể sync từ Google Sheets sang Airtable hoặc ngược lại
            
            logger.info(f"Đồng bộ database cho kênh {channel_id} thành công")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi khi đồng bộ database cho kênh {channel_id}: {str(e)}")
            return False
    
    async def get_channel_records(self, channel_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Lấy records từ database của một kênh
        """
        try:
            airtable_client = self._get_airtable_client(channel_id)
            
            if airtable_client:
                records = await asyncio.to_thread(
                    airtable_client.get_all,
                    max_records=limit,
                    sort=[("Created At", "desc")]
                )
                return [record['fields'] for record in records]
            
            return []
            
        except Exception as e:
            logger.error(f"Lỗi khi lấy records cho kênh {channel_id}: {str(e)}")
            return []

    def _calculate_next_stt_from_values(self, all_values: list) -> int:
        """
        Tính STT tiếp theo từ dữ liệu đã có (không cần gọi API lại)
        """
        try:
            max_stt = 0
            
            logger.debug(f"Calculating STT from {len(all_values)} rows")
            
            for i, row in enumerate(all_values):
                if len(row) > 0 and str(row[0]).isdigit():
                    current_stt = int(row[0])
                    max_stt = max(max_stt, current_stt)
                    logger.debug(f"Row {i+1}: STT = {current_stt}, Max STT = {max_stt}")
            
            next_stt = max_stt + 1
            logger.info(f"Calculated next STT: {next_stt} (from {len(all_values)} rows, max_stt: {max_stt})")
            return next_stt
            
        except Exception as e:
            logger.error(f"Lỗi khi tính STT từ values: {str(e)}")
            # Fallback: đếm data rows + 1
            data_rows = len([row for row in all_values if any(cell.strip() for cell in row if cell)])
            fallback_stt = max(data_rows, 1)
            logger.warning(f"Fallback STT: {fallback_stt}")
            return fallback_stt

    def _get_next_stt(self, worksheet) -> int:
        """
        Lấy STT tiếp theo dựa trên dữ liệu hiện có trong sheet
        """
        try:
            all_values = worksheet.get_all_values()
            max_stt = 0
            
            logger.debug(f"Tổng số rows trong sheet: {len(all_values)}")
            
            for i, row in enumerate(all_values):
                if i == 0:  # Skip header row
                    continue
                if len(row) > 0 and str(row[0]).isdigit():
                    current_stt = int(row[0])
                    max_stt = max(max_stt, current_stt)
                    logger.debug(f"Row {i+1}: STT = {current_stt}, Max STT = {max_stt}")
            
            next_stt = max_stt + 1
            logger.info(f"Calculated next STT: {next_stt} (based on max_stt: {max_stt})")
            return next_stt
            
        except Exception as e:
            logger.error(f"Lỗi khi tính STT: {str(e)}")
            # Fallback an toàn: đếm rows có data (trừ header) + 1
            try:
                all_values = worksheet.get_all_values()
                data_rows = len([row for row in all_values[1:] if any(cell.strip() for cell in row if cell)])
                fallback_stt = data_rows + 1
                logger.warning(f"Fallback STT calculation: {fallback_stt} (data rows: {data_rows})")
                return fallback_stt
            except:
                logger.error("Fallback STT calculation cũng thất bại, sử dụng STT = 1")
                return 1


# Singleton instance
database_manager = DatabaseManager() 