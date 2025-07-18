from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from typing import List, Optional, Dict, Any
import uvicorn
import logging
import os
from datetime import datetime
import uuid
import sys
import pathlib
import json
import re


def sanitize_filename(filename: str) -> str:
    """Sanitizes a filename by removing special characters and replacing spaces."""
    if not filename:
        return ""
    # Replace spaces and known problematic characters with underscore
    filename = re.sub(r'[\\s/\\\\:*?"<>|]+', '_', filename)
    # Remove any other non-alphanumeric, non-dot, non-underscore, non-hyphen characters
    filename = re.sub(r'[^\\w\\.\\-_]', '', filename)
    # Collapse multiple underscores
    filename = re.sub(r'__+', '_', filename)
    return filename


# Thêm thư mục gốc vào sys.path
root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.models import InputData, ContentPackage, WorkflowConfig, ChannelConfig
from src.workflow_engine import workflow_engine
from src.channel_manager import channel_manager
from src.video_service import video_extractor
from config.settings import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(settings.logs_path, 'app.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Tạo FastAPI app
app = FastAPI(
    title="YouTube Content Automation System",
    description="Hệ thống tự động hóa tạo nội dung YouTube với AI - Multi Channel Support",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Tạo các thư mục cần thiết nếu chưa tồn tại
static_dir = os.path.join(root_dir, "static")
templates_dir = os.path.join(root_dir, "templates")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(templates_dir, exist_ok=True)

# Mount static files và templates
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/images", StaticFiles(directory=settings.images_storage_path), name="images")
templates = Jinja2Templates(directory=templates_dir)

# Đảm bảo thư mục cần thiết tồn tại
os.makedirs(settings.data_storage_path, exist_ok=True)
os.makedirs(settings.images_storage_path, exist_ok=True)
os.makedirs(settings.logs_path, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Trang chủ với form tạo content và quản lý channels"""
    try:
        # Lấy danh sách channels
        channels = channel_manager.get_active_channels()
        channel_data = {c.channel_name: c.channel_id for c in channels}
        
        # Lấy thống kê
        workflow_stats = workflow_engine.get_channel_statistics()
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "channels": channels,
            "channels_json": json.dumps(channel_data),
            "workflow_stats": workflow_stats
        })
    except Exception as e:
        logger.error(f"Lỗi trang chủ: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Lỗi máy chủ nội bộ: {e}")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, channel_id: Optional[str] = None):
    """Dashboard hiển thị packages theo channel"""
    try:
        # Lấy packages
        if channel_id:
            packages = workflow_engine.get_packages_by_channel(channel_id)
            channel = channel_manager.get_channel(channel_id)
        else:
            packages = list(workflow_engine.get_all_active_packages().values())
            channel = None
        
        # Lấy thống kê
        channel_stats = workflow_engine.get_channel_statistics()
        all_channels = channel_manager.get_all_channels()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "packages": packages,
            "current_channel": channel,
            "channel_id": channel_id,
            "channel_stats": channel_stats,
            "all_channels": all_channels
        })
    except Exception as e:
        logger.error(f"Lỗi dashboard: {str(e)}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": f"Lỗi khi tải dashboard: {str(e)}"
        }, status_code=500)








# === CONTENT GENERATION ENDPOINTS ===

@app.post("/api/create-content")
async def create_content(
    background_tasks: BackgroundTasks,
    channel_name: str = Form(...),
    channel_description: str = Form(...),
    video_topic: str = Form(...),
    additional_context: Optional[str] = Form(None),
    video_frame: Optional[UploadFile] = File(None),
    video_file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    video_timestamp: Optional[float] = Form(None)
):
    """Tạo nội dung mới từ thông tin kênh nhập trực tiếp"""
    try:
        # Tìm channel_id dựa trên channel_name
        channel_id = None
        for cid, channel in channel_manager.get_all_channels().items():
            if channel.channel_name.lower().strip() == channel_name.lower().strip():
                channel_id = cid
                break
        
        # Tạo input data từ form
        input_data = InputData(
            channel_id=channel_id,  # Set channel_id để routing đúng sheet
            channel_name=channel_name,
            channel_description=channel_description,
            video_topic=video_topic,
            additional_context=additional_context
        )
        
        # Xử lý frame video với các phương thức khác nhau
        frame_extracted = False
        
        try:
            # Phương thức 1: Upload ảnh trực tiếp
            if video_frame:
                logger.info("Xử lý upload ảnh frame trực tiếp")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # Sanitize filename
                safe_filename = sanitize_filename(video_frame.filename)
                filename = f"frame_{timestamp}_{uuid.uuid4().hex[:8]}_{safe_filename}"
                file_path = os.path.join(settings.images_storage_path, filename)
                
                with open(file_path, "wb") as f:
                    content = await video_frame.read()
                    f.write(content)
                
                input_data.video_frame_file = file_path
                input_data.video_frame_url = f"/images/{filename}"
                frame_extracted = True
            
            # Phương thức 2: Upload video file và trích xuất frame
            elif video_file:
                logger.info("Xử lý upload video file và trích xuất frame")
                
                # Lưu video file tạm thời
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_video_filename = sanitize_filename(video_file.filename)
                video_filename = f"video_{timestamp}_{uuid.uuid4().hex[:8]}_{safe_video_filename}"
                video_path = os.path.join(settings.images_storage_path, video_filename)
                
                with open(video_path, "wb") as f:
                    content = await video_file.read()
                    f.write(content)
                
                try:
                    # Trích xuất frame từ video
                    frame_path, frame_url = await video_extractor.extract_frame_from_local_video(
                        video_path, 
                        video_timestamp
                    )
                    
                    input_data.video_frame_file = frame_path
                    input_data.video_frame_url = frame_url
                    input_data.video_file = video_path
                    input_data.video_timestamp = video_timestamp
                    frame_extracted = True
                    
                    logger.info(f"Đã trích xuất frame từ video: {frame_path}")
                    
                finally:
                    # Xóa file video tạm thời
                    if os.path.exists(video_path):
                        os.remove(video_path)
            
            # Phương thức 3: YouTube URL và trích xuất frame
            elif youtube_url:
                logger.info(f"Xử lý YouTube URL và trích xuất frame: {youtube_url}")
                
                # Validate YouTube URL
                if not video_extractor.validate_youtube_url(youtube_url):
                    raise HTTPException(status_code=400, detail="URL YouTube không hợp lệ")
                
                # Trích xuất frame từ YouTube
                frame_path, frame_url = await video_extractor.extract_frame_from_youtube(
                    youtube_url, 
                    video_timestamp
                )
                
                input_data.video_frame_file = frame_path
                input_data.video_frame_url = frame_url
                input_data.youtube_url = youtube_url
                input_data.video_timestamp = video_timestamp
                frame_extracted = True
                
                logger.info(f"Đã trích xuất frame từ YouTube: {frame_path}")
                
        except Exception as e:
            logger.error(f"Lỗi xử lý video frame: {str(e)}")
            # Không raise exception, chỉ log và tiếp tục không có frame
            logger.warning("Tiếp tục xử lý mà không có frame video")
        
        # Chạy workflow để tạo 1 content trong background
        async def process_single_content():
            try:
                # Chạy workflow cho 1 content duy nhất
                logger.info(f"Bắt đầu tạo content cho topic: {input_data.video_topic}")
                await workflow_engine.run_full_workflow(input_data)
                logger.info("Hoàn thành tạo content")
                
            except Exception as e:
                logger.error(f"Lỗi xử lý content: {str(e)}")
        
        background_tasks.add_task(process_single_content)
        
        return {
            "success": True,
            "message": f"Đã bắt đầu tạo nội dung cho kênh {channel_name}",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi tạo content: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))





@app.get("/api/packages/{package_id}")
async def get_package_status(package_id: str):
    """Lấy trạng thái của một package"""
    try:
        package = workflow_engine.get_package_status(package_id)
        
        if not package:
            raise HTTPException(status_code=404, detail="Không tìm thấy package")
        
        return {
            "package_id": package.id,
            "channel_id": package.channel_id,
            "status": package.status,
            "created_at": package.created_at,
            "updated_at": package.updated_at,
            "content": package.generated_content.dict() if package.generated_content else None,
            "images": package.generated_images.dict() if package.generated_images else None,
            "logs": package.processing_logs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi lấy package status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))





@app.get("/api/packages")
async def get_all_packages():
    """Lấy tất cả packages"""
    try:
        packages = workflow_engine.get_all_active_packages()
        
        result = []
        for package in packages.values():
            result.append({
                "package_id": package.id,
                "channel_id": package.channel_id,
                "channel_name": package.input_data.channel_name,
                "status": package.status.value,
                "created_at": package.created_at.isoformat(),
                "title": package.generated_content.title if package.generated_content else "Đang tạo...",
                "logs": package.processing_logs[-2:],
                "video_frame_url": package.input_data.video_frame_url,
                "thumbnail_url": package.generated_images.thumbnail_url if package.generated_images else None
            })
        
        return {"packages": result}
        
    except Exception as e:
        logger.error(f"Lỗi lấy all packages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))





@app.get("/health")
async def health_check():
    """Kiểm tra health của hệ thống"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }


@app.get("/api/package/{package_id}")
async def get_package_detail(package_id: str):
    """Lấy chi tiết của một package"""
    try:
        package = workflow_engine.get_package_status(package_id)
        
        if not package:
            # Tạo dữ liệu giả khi không tìm thấy package
            logger.warning(f"Không tìm thấy package {package_id}, trả về dữ liệu giả")
            
            # Trích xuất thông tin từ package_id
            # Format: pkg_YYYYMMDDHHMMSS_XXXX
            try:
                date_part = package_id.split('_')[1]
                created_date = datetime.strptime(date_part, '%Y%m%d%H%M%S')
            except:
                created_date = datetime.now()
            
            from src.models import InputData, GeneratedContent, GeneratedImages, ContentStatus
            
            # Tạo dữ liệu giả
            return {
                "id": package_id,
                "channel_id": "recovered-channel",
                "status": "generated",
                "created_at": created_date,
                "updated_at": datetime.now(),
                "input_data": {
                    "channel_name": "Kênh phục hồi",
                    "channel_description": "Dữ liệu gốc đã bị mất khi khởi động lại server"
                },
                "generated_content": {
                    "title": "Nội dung đã được tạo nhưng dữ liệu đã bị mất",
                    "description": "Dữ liệu chi tiết đã bị mất do server khởi động lại. Hệ thống chỉ lưu dữ liệu trong bộ nhớ tạm thời.",
                    "tags": ["recovered", "data-lost"],
                    "thumbnail_name": "recovered-thumbnail"
                },
                "generated_images": None,
                "processing_logs": [
                    f"{datetime.now().isoformat()}: Dữ liệu gốc đã bị mất khi khởi động lại server",
                    f"{datetime.now().isoformat()}: Đây là dữ liệu phục hồi tạm thời"
                ]
            }
        
        return {
            "id": package.id,
            "channel_id": package.channel_id,
            "status": package.status.value,
            "created_at": package.created_at,
            "updated_at": package.updated_at,
            "input_data": package.input_data,
            "generated_content": package.generated_content,
            "generated_images": package.generated_images,
            "processing_logs": package.processing_logs
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi lấy package detail: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/packages/{package_id}/select-image")
async def select_image(package_id: str, request: dict):
    """Cập nhật ảnh được chọn cho package"""
    try:
        selected_image_url = request.get("selected_image_url")
        
        if not selected_image_url:
            raise HTTPException(status_code=400, detail="Thiếu selected_image_url")
        
        # Lấy package từ workflow engine
        package = workflow_engine.get_package_status(package_id)
        
        if not package:
            raise HTTPException(status_code=404, detail="Không tìm thấy package")
        
        # Cập nhật selected_image_url
        if package.generated_images:
            package.generated_images.selected_image_url = selected_image_url
            package.add_log(f"Đã chọn ảnh: {selected_image_url}")
            
            # Cập nhật vào database - sử dụng phương thức tối ưu chỉ update cột H
            from src.database_service import database_manager
            success = await database_manager.update_selected_image(
                package_id=package_id,
                channel_id=package.channel_id,
                selected_image_url=selected_image_url
            )
            
            if success:
                logger.info(f"Đã cập nhật ảnh được chọn cho package {package_id} trong luồng")
                return {
                    "success": True,
                    "message": "Đã cập nhật ảnh được chọn trong luồng",
                    "selected_image_url": selected_image_url
                }
            else:
                logger.warning(f"Không thể cập nhật database cho package {package_id}")
                return {
                    "success": True,
                    "message": "Đã cập nhật ảnh được chọn (chưa đồng bộ database)",
                    "selected_image_url": selected_image_url
                }
        else:
            raise HTTPException(status_code=400, detail="Package không có ảnh được tạo")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi cập nhật ảnh được chọn: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 