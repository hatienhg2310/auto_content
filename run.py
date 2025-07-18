#!/usr/bin/env python3
"""
YouTube Content Automation System


Script chạy ứng dụng
"""

import sys
import os
import subprocess
from pathlib import Path

def check_requirements():
    """Kiểm tra requirements.txt"""
    try:
        import fastapi
        import uvicorn
        import openai
        import gspread
        import pydantic_settings
        print("✅ Tất cả dependencies đã được cài đặt")
        return True
    except ImportError as e:
        print(f"❌ Thiếu dependency: {e}")
        print("Chạy: pip install -r requirements.txt")
        return False

def check_env_file():
    """Kiểm tra file .env"""
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    if not env_path.exists():
        if env_example_path.exists():
            print("❌ File .env không tồn tại")
            print("Tạo file .env từ .env.example và cấu hình các API keys")
            return False
        else:
            print("❌ Cả .env và .env.example đều không tồn tại")
            return False
    
    print("✅ File .env đã tồn tại")
    return True

def check_directories():
    """Tạo các thư mục cần thiết"""
    directories = ["data", "data/images", "logs", "templates", "static"]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print("✅ Các thư mục đã được tạo/kiểm tra")

def main():
    """Hàm chính"""
    print("🚀 YouTube Content Automation System")
    print("👨‍💻 Developed by: Team AI")
    print("=" * 50)
    
    # Kiểm tra dependencies
    if not check_requirements():
        sys.exit(1)
    
    # Kiểm tra file .env
    if not check_env_file():
        sys.exit(1)
    
    # Tạo thư mục
    check_directories()
    
    # Chạy ứng dụng
    print("\n🔥 Đang khởi động ứng dụng...")
    print("📱 Truy cập: http://localhost:8000")
    print("📊 Dashboard: http://localhost:8000/dashboard")
    print("🔍 API Docs: http://localhost:8000/docs")
    print("\n⏹️  Nhấn Ctrl+C để dừng")
    print("=" * 50)
    
    try:
        # Import và chạy ứng dụng
        from src.main import app
        import uvicorn
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=True
        )
        
    except KeyboardInterrupt:
        print("\n👋 Đã dừng ứng dụng")
    except Exception as e:
        print(f"\n❌ Lỗi khi chạy ứng dụng: {e}")
        print("\nKiểm tra:")
        print("1. File .env đã được cấu hình đúng")
        print("2. Tất cả API keys đã hợp lệ")
        print("3. Google credentials file tồn tại")
        sys.exit(1)

if __name__ == "__main__":
    main() 