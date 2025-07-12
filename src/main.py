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

# Thêm thư mục gốc vào sys.path
root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.models import InputData, ContentPackage, WorkflowConfig, ChannelConfig
from src.workflow_engine import workflow_engine
from src.channel_manager import channel_manager
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


@app.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request):
    """Trang quản lý channels"""
    try:
        channels = channel_manager.get_all_channels()
        
        # Tạo channel stats
        channel_stats = {
            "total_channels": len(channels),
            "active_channels": sum(1 for c in channels.values() if c.is_active),
            "channels_with_airtable": sum(1 for c in channels.values() if getattr(c, 'airtable_base_id', None)),
            "channels_with_google_sheets": sum(1 for c in channels.values() if getattr(c, 'google_sheets_id', None))
        }
        
        return templates.TemplateResponse("channels.html", {
            "request": request,
            "channels": channels,
            "channel_stats": channel_stats
        })
    except Exception as e:
        logger.error(f"Lỗi trang channels: {str(e)}")
        # Trả về HTMLResponse thay vì dict
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": f"Lỗi khi tải trang kênh: {str(e)}"
        }, status_code=500)


# === CHANNEL MANAGEMENT ENDPOINTS ===

@app.post("/api/channels")
async def create_channel(
    channel_id: str = Form(...),
    channel_name: str = Form(...),
    channel_description: str = Form(...),
    content_style: Optional[str] = Form(None),
    target_audience: Optional[str] = Form(None),
    content_topics: Optional[str] = Form(None)
):
    """Tạo kênh mới"""
    try:
        # Kiểm tra channel đã tồn tại
        if channel_manager.get_channel(channel_id):
            raise HTTPException(status_code=400, detail="Channel ID đã tồn tại")
        
        # Tạo ChannelConfig
        topics_list = [topic.strip() for topic in content_topics.split(",")] if content_topics else []
        
        channel_config = ChannelConfig(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_description=channel_description,
            content_style=content_style,
            target_audience=target_audience,
            content_topics=topics_list
        )
        
        # Thêm channel
        success = channel_manager.add_channel(channel_config)
        
        if success:
            return {"success": True, "message": f"Đã tạo kênh {channel_name} thành công"}
        else:
            raise HTTPException(status_code=500, detail="Lỗi khi tạo kênh")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi tạo kênh: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/channels")
async def get_channels():
    """Lấy danh sách tất cả channels"""
    try:
        channels = channel_manager.get_all_channels()
        
        return {
            "channels": {channel_id: channel.dict() for channel_id, channel in channels.items()}
        }
    except Exception as e:
        logger.error(f"Lỗi lấy channels: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/channels/{channel_id}")
async def get_channel(channel_id: str):
    """Lấy thông tin một channel"""
    try:
        channel = channel_manager.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
        
        setup_status = channel_manager.validate_channel_setup(channel_id)
        
        return {
            "channel": channel.dict(),
            "setup_status": setup_status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi lấy channel: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/channels/{channel_id}")
async def update_channel(
    channel_id: str,
    channel_name: str = Form(...),
    channel_description: str = Form(...),
    content_style: Optional[str] = Form(None),
    target_audience: Optional[str] = Form(None),
    content_topics: Optional[str] = Form(None),
    is_active: bool = Form(True)
):
    """Cập nhật thông tin channel"""
    try:
        existing_channel = channel_manager.get_channel(channel_id)
        if not existing_channel:
            raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
        
        # Parse topics
        topics_list = [topic.strip() for topic in content_topics.split(",")] if content_topics else []
        
        # Tạo channel config mới
        updated_channel = ChannelConfig(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_description=channel_description,
            content_style=content_style,
            target_audience=target_audience,
            content_topics=topics_list,
            is_active=is_active
        )
        
        # Cập nhật channel
        success = channel_manager.update_channel(channel_id, updated_channel)
        
        if success:
            return {"success": True, "message": f"Đã cập nhật kênh {channel_name} thành công"}
        else:
            raise HTTPException(status_code=500, detail="Lỗi khi cập nhật kênh")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi cập nhật kênh: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: str):
    """Xóa kênh"""
    try:
        success = channel_manager.remove_channel(channel_id)
        
        if success:
            return {"success": True, "message": f"Đã xóa kênh {channel_id} thành công"}
        else:
            raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi xóa kênh: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# === CONTENT GENERATION ENDPOINTS ===

@app.post("/api/create-content")
async def create_content(
    background_tasks: BackgroundTasks,
    channel_name: str = Form(...),
    channel_description: str = Form(...),
    video_topic: str = Form(...),
    additional_context: Optional[str] = Form(None),
    video_frame: Optional[UploadFile] = File(None)
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
        
        # Xử lý file ảnh nếu có
        if video_frame:
            # Tạo thư mục lưu ảnh tạm
            temp_dir = os.path.join(settings.data_storage_path, "temp_frames")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Lưu file
            file_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}_{video_frame.filename}")
            with open(file_path, "wb") as f:
                content = await video_frame.read()
                f.write(content)
            
            # Cập nhật đường dẫn file
            input_data.video_frame_file = file_path
        
        # Chạy workflow để tạo 5 content khác nhau trong background
        async def process_multiple_content():
            try:
                # Tạo 5 InputData với variations khác nhau
                input_data_list = []
                base_topic = input_data.video_topic
                
                # Tạo 5 variations với approach khác nhau cho content đa dạng
                for i in range(5):
                    # Tạo input data cho mỗi variation với approach khác nhau
                    variation_input = InputData(
                        channel_id=input_data.channel_id,
                        channel_name=input_data.channel_name,
                        channel_description=input_data.channel_description,
                        video_topic=base_topic,  # Giữ nguyên topic gốc
                        additional_context=f"{input_data.additional_context or ''} | Generate unique variation #{i+1}",
                        video_frame_file=input_data.video_frame_file  # Dùng chung frame
                    )
                    input_data_list.append(variation_input)
                
                # Chạy batch workflow cho 5 content
                logger.info(f"Bắt đầu tạo 5 content variations cho topic: {base_topic}")
                await workflow_engine.run_batch_workflow(input_data_list)
                logger.info("Hoàn thành tạo 5 content variations")
                
            except Exception as e:
                logger.error(f"Lỗi xử lý multiple content: {str(e)}")
        
        background_tasks.add_task(process_multiple_content)
        
        return {
            "success": True,
            "message": f"Đã bắt đầu tạo nội dung cho kênh {channel_name}",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi tạo content: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/channels/{channel_id}/batch-create")
async def create_batch_content(
    channel_id: str,
    background_tasks: BackgroundTasks,
    topics: List[str] = Form(...),
    additional_context: Optional[str] = Form(None)
):
    """Tạo nhiều nội dung cùng lúc cho một kênh"""
    try:
        # Kiểm tra channel tồn tại
        channel = channel_manager.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
        
        # Tạo input data cho từng topic
        input_data_list = []
        for topic in topics:
            input_data = InputData(
                channel_id=channel_id,
                video_topic=topic.strip(),
                additional_context=additional_context
            )
            input_data_list.append(input_data)
        
        # Chạy batch workflow trong background
        async def process_batch():
            try:
                await workflow_engine.run_channel_batch(channel_id, input_data_list)
            except Exception as e:
                logger.error(f"Lỗi xử lý batch: {str(e)}")
        
        background_tasks.add_task(process_batch)
        
        return {
            "success": True,
            "message": f"Đã bắt đầu tạo {len(topics)} nội dung cho kênh {channel.channel_name}",
            "channel_id": channel_id,
            "topic_count": len(topics)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi tạo batch content: {str(e)}")
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


@app.get("/api/channels/{channel_id}/packages")
async def get_channel_packages(channel_id: str):
    """Lấy tất cả packages của một kênh"""
    try:
        # Kiểm tra channel tồn tại
        channel = channel_manager.get_channel(channel_id)
        if not channel:
            raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
        
        packages = workflow_engine.get_packages_by_channel(channel_id)
        
        result = []
        for package in packages:
            result.append({
                "package_id": package.id,
                "status": package.status,
                "created_at": package.created_at,
                "title": package.generated_content.title if package.generated_content else None,
                "thumbnail_url": package.generated_images.thumbnail_url if package.generated_images else None
            })
        
        return {
            "channel_id": channel_id,
            "channel_name": channel.channel_name,
            "packages": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi lấy channel packages: {str(e)}")
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
                "status": package.status,
                "created_at": package.created_at,
                "title": package.generated_content.title if package.generated_content else None
            })
        
        return {"packages": result}
        
    except Exception as e:
        logger.error(f"Lỗi lấy all packages: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cleanup")
async def cleanup_packages():
    """Dọn dẹp packages cũ"""
    try:
        await workflow_engine.cleanup_completed_packages(max_age_hours=24)
        return {"success": True, "message": "Đã dọn dẹp packages cũ"}
        
    except Exception as e:
        logger.error(f"Lỗi cleanup packages: {str(e)}")
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 