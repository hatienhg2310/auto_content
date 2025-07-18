from pydantic_settings import BaseSettings
from typing import Optional
import os
from pathlib import Path
from pydantic import Field


class Settings(BaseSettings):
    """
    Cấu hình ứng dụng YouTube Content Automation
    """
    
    # AI Configuration - Gemini API (Primary)
    gemini_api_key: str = Field("your-gemini-api-key", env="GEMINI_API_KEY")
    
    # OpenAI Configuration (Fallback)
    openai_api_key: str = Field("sk-your-openai-api-key", env="OPENAI_API_KEY")
    
    # Midjourney/Image Generation
    midjourney_api_key: Optional[str] = Field(None, env="MIDJOURNEY_API_KEY")
    midjourney_server_id: Optional[str] = Field(None, env="MIDJOURNEY_SERVER_ID")
    midjourney_channel_id: Optional[str] = Field(None, env="MIDJOURNEY_CHANNEL_ID")
    
    # Piapi.ai (Midjourney API Service)
    piapi_api_key: Optional[str] = Field(None, env="PIAPI_API_KEY")
    
    # Google APIs
    google_credentials_file: str = Field("credentials.json")
    google_sheets_id: str = Field("your-google-sheets-id")
    
    # Airtable
    airtable_api_key: str = Field("your-airtable-api-key")
    airtable_base_id: str = Field("your-airtable-base-id")
    airtable_table_name: str = "youtube_content"
    
    # YouTube API
    youtube_api_key: str = Field("your-youtube-api-key")
    youtube_client_secrets_file: str = Field("client_secrets.json")
    
    # Application Settings
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True
    
    # Storage Paths
    data_storage_path: str = "./data"
    images_storage_path: str = "./data/images"
    logs_path: str = "./logs"
    
    # Content Creator Info
    channel_owner_name: str = "Team AI"
    default_channel_name: str = Field("Demo Channel")
    default_channel_description: str = Field("Kênh demo để thử nghiệm tạo nội dung tự động")
    
    # AI Services API Keys
    midjourney_api_key: Optional[str] = Field(None, env="MIDJOURNEY_API_KEY")
    
    # Midjourney Integration Options
    # Option 1: Replicate API (Recommended)
    replicate_api_token: Optional[str] = Field(None, env="REPLICATE_API_TOKEN")
    
    # Option 2: GoAPI (Midjourney API Service)
    goapi_token: Optional[str] = Field(None, env="GOAPI_TOKEN")
    
    # Option 3: Discord Bot Integration
    midjourney_server_id: Optional[str] = Field(None, env="MIDJOURNEY_SERVER_ID")
    midjourney_channel_id: Optional[str] = Field(None, env="MIDJOURNEY_CHANNEL_ID")
    discord_bot_token: Optional[str] = Field(None, env="DISCORD_BOT_TOKEN")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Tạo các thư mục cần thiết
        Path(self.data_storage_path).mkdir(parents=True, exist_ok=True)
        Path(self.images_storage_path).mkdir(parents=True, exist_ok=True)
        Path(self.logs_path).mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings() 