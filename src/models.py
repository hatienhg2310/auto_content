from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class ContentStatus(str, Enum):
    """Trạng thái của nội dung"""
    PENDING = "pending"
    PROCESSING = "processing"
    GENERATING_CONTENT = "generating_content"
    GENERATED = "generated"
    UPLOADED = "uploaded"
    PUBLISHED = "published"
    FAILED = "failed"


class ChannelConfig(BaseModel):
    """Cấu hình cho từng kênh YouTube"""
    channel_id: str = Field(..., description="ID của kênh")
    channel_name: str = Field(..., description="Tên kênh YouTube")
    channel_description: str = Field(..., description="Mô tả về kênh")
    
    # Cấu hình content cho kênh
    content_style: Optional[str] = Field(None, description="Phong cách nội dung")
    target_audience: Optional[str] = Field(None, description="Đối tượng khán giả mục tiêu")
    content_topics: List[str] = Field([], description="Danh sách các chủ đề nội dung chính")
    
    # Database integrations
    airtable_base_id: Optional[str] = Field(None, description="Airtable Base ID")
    airtable_table_name: Optional[str] = Field("Content", description="Airtable Table Name")
    google_sheets_id: Optional[str] = Field(None, description="Google Sheets ID")
    google_sheet_name: Optional[str] = Field(None, description="Tên sheet trong Google Sheets (cho multi-sheet)")
    google_sheet_gid: Optional[str] = Field(None, description="GID của sheet tab cụ thể")
    google_sheet_url: Optional[str] = Field(None, description="URL đầy đủ của Google Sheet")
    
    # Metadata
    created_by: str = Field(default="Anh Hà Tiến", description="Người quản lý kênh")
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(True, description="Kênh có đang hoạt động không")


class InputData(BaseModel):
    """Dữ liệu đầu vào cho hệ thống"""
    # --- Thông tin kênh (có thể được cung cấp trực tiếp hoặc auto-filled) ---
    channel_name: Optional[str] = Field(None, description="Tên kênh")
    channel_description: Optional[str] = Field(None, description="Mô tả kênh")

    # --- ID kênh (nếu sử dụng kênh đã quản lý) ---
    channel_id: Optional[str] = None
    
    # --- Thông tin video ---
    video_topic: Optional[str] = Field(None, description="Chủ đề của video")
    video_frame_file: Optional[str] = Field(None, description="Đường dẫn đến file ảnh frame")
    additional_context: Optional[str] = Field(None, description="Thông tin bổ sung")
    video_frame_url: Optional[str] = Field(None, description="URL frame video tham khảo")
    created_by: str = Field(default="Anh Hà Tiến", description="Người tạo")
    created_at: datetime = Field(default_factory=datetime.now)


class GeneratedContent(BaseModel):
    """Nội dung được tạo ra bởi AI"""
    title: str = Field(..., description="Tiêu đề video")
    description: str = Field(..., description="Mô tả video")
    tags: List[str] = Field(..., description="Danh sách tags")
    thumbnail_name: str = Field(..., description="Tên thumbnail")
    image_prompts: List[str] = Field(..., description="Prompts để tạo ảnh")


class GeneratedImages(BaseModel):
    """Ảnh được tạo ra"""
    thumbnail_url: Optional[str] = Field(None, description="URL thumbnail chính")
    thumbnail_file: Optional[str] = Field(None, description="Tên file thumbnail") 
    
    # Thêm hỗ trợ cho 4 URLs từ Midjourney
    midjourney_urls: List[str] = Field(default_factory=list, description="Danh sách 4 URLs từ Midjourney")
    
    additional_images: List[Dict[str, Any]] = Field(default_factory=list, description="Các ảnh bổ sung với metadata")
    image_generation_prompts: List[str] = Field(default_factory=list, description="Prompts đã sử dụng")
    
    def get_display_urls(self) -> str:
        """Trả về chuỗi URLs để hiển thị/lưu trữ"""
        if self.midjourney_urls:
            return " | ".join(self.midjourney_urls)
        return self.thumbnail_url or ""


class YouTubeVideoData(BaseModel):
    """Dữ liệu video YouTube"""
    video_id: Optional[str] = Field(None, description="ID video trên YouTube")
    video_url: Optional[str] = Field(None, description="URL video")
    upload_status: Optional[str] = Field(None, description="Trạng thái upload")
    published_at: Optional[datetime] = Field(None, description="Thời gian publish")


class ContentPackage(BaseModel):
    """Gói nội dung hoàn chỉnh"""
    id: str = Field(..., description="ID duy nhất của package")
    channel_id: str = Field(..., description="ID kênh YouTube")
    input_data: InputData
    generated_content: Optional[GeneratedContent] = None
    generated_images: Optional[GeneratedImages] = None
    youtube_data: Optional[YouTubeVideoData] = None
    status: ContentStatus = Field(default=ContentStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    processing_logs: List[str] = Field(default_factory=list)
    
    def add_log(self, message: str):
        """Thêm log vào quá trình xử lý"""
        self.processing_logs.append(f"{datetime.now().isoformat()}: {message}")
        self.updated_at = datetime.now()
        
    def log(self, message: str):
        """Alias cho add_log để tương thích với code cũ"""
        self.add_log(message)
        
    def update_status(self, new_status: ContentStatus):
        """Cập nhật trạng thái và thêm log"""
        self.status = new_status
        self.add_log(f"Cập nhật trạng thái: {new_status.value}")


class WorkflowConfig(BaseModel):
    """Cấu hình workflow"""
    auto_generate_content: bool = True
    auto_generate_images: bool = True  # Bật lại để generate images qua Midjourney
    
    # AI Configuration
    openai_model: str = "gpt-4"
    max_title_length: int = 100
    max_description_length: int = 5000
    number_of_tags: int = 15
    
    # Image Generation
    enable_midjourney_generation: bool = True  # Use Midjourney over DALL-E when available
    thumbnail_size: tuple = (1280, 720)
    image_quality: str = "high"
    
    class Config:
        arbitrary_types_allowed = True


class DatabaseRecord(BaseModel):
    """Record để lưu vào database (Google Sheets/Airtable)"""
    package_id: str = Field(..., description="ID của package")
    channel_id: str = Field(..., description="ID kênh")
    channel_name: str = Field(..., description="Tên kênh")
    video_title: str = Field(..., description="Tiêu đề video")
    thumbnail_name: str = Field(..., description="Tên thumbnail")
    video_description: str = Field(..., description="Mô tả video")
    video_tags: str = Field(..., description="Tags (phân cách bằng dấu phẩy)")
    thumbnail_image_url: str = Field(default="", description="URL ảnh thumbnail")
    video_url: str = Field(default="", description="URL video")
    status: str = Field(..., description="Trạng thái")
    created_by: str = Field(..., description="Người tạo")
    created_at: str = Field(..., description="Thời gian tạo")
    updated_at: str = Field(..., description="Thời gian cập nhật")


class ChannelDatabase(BaseModel):
    """Cấu hình database cho từng kênh"""
    channel_id: str = Field(..., description="ID kênh")
    google_sheets_id: Optional[str] = Field(None, description="Google Sheets ID riêng cho kênh")
    google_sheet_name: Optional[str] = Field(None, description="Tên sheet trong Google Sheets")
    google_sheet_gid: Optional[str] = Field(None, description="GID của sheet tab cụ thể")
    google_sheet_url: Optional[str] = Field(None, description="URL đầy đủ của Google Sheet (bao gồm gid)")
    airtable_base_id: Optional[str] = Field(None, description="Airtable Base ID riêng cho kênh")
    airtable_table_name: str = Field("Content", description="Tên table trong Airtable")
    
    def parse_google_sheet_url(self) -> tuple[Optional[str], Optional[str]]:
        """
        Parse Google Sheet URL để lấy sheets_id và gid
        Returns: (sheets_id, gid)
        """
        if not self.google_sheet_url:
            return self.google_sheets_id, self.google_sheet_gid
            
        import re
        
        # Parse spreadsheet ID từ URL
        spreadsheet_pattern = r'/spreadsheets/d/([a-zA-Z0-9-_]+)'
        spreadsheet_match = re.search(spreadsheet_pattern, self.google_sheet_url)
        sheets_id = spreadsheet_match.group(1) if spreadsheet_match else self.google_sheets_id
        
        # Parse GID từ URL  
        gid_pattern = r'[#&]gid=([0-9]+)'
        gid_match = re.search(gid_pattern, self.google_sheet_url)
        gid = gid_match.group(1) if gid_match else self.google_sheet_gid
        
        return sheets_id, gid 