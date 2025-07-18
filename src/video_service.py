import cv2
import yt_dlp
import os
import tempfile
import logging
from typing import Optional, Tuple
import uuid
from datetime import datetime
import asyncio
import aiofiles
from pathlib import Path

logger = logging.getLogger(__name__)


class VideoFrameExtractor:
    """
    Service chuyên nghiệp để trích xuất frame từ video local và YouTube
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            # Import settings here to avoid circular imports
            import sys
            import pathlib
            root_dir = str(pathlib.Path(__file__).parent.parent.absolute())
            if root_dir not in sys.path:
                sys.path.append(root_dir)
            from config.settings import settings
            output_dir = settings.images_storage_path
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cấu hình yt-dlp
        self.ydl_opts = {
            'format': 'best[height<=720]',  # Tối ưu chất lượng
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'outtmpl': str(self.output_dir / 'temp_%(id)s.%(ext)s'),
        }
    
    async def extract_frame_from_local_video(
        self, 
        video_path: str, 
        timestamp: Optional[float] = None
    ) -> Tuple[str, str]:
        """
        Trích xuất frame từ video local
        
        Args:
            video_path: Đường dẫn đến file video
            timestamp: Thời điểm lấy frame (giây), None = giữa video
            
        Returns:
            Tuple[file_path, url_path]: Đường dẫn file và URL
        """
        try:
            logger.info(f"Trích xuất frame từ video local: {video_path}")
            
            # Kiểm tra file tồn tại
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file không tồn tại: {video_path}")
            
            # Mở video
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Không thể mở video: {video_path}")
            
            try:
                # Lấy thông tin video
                fps = cap.get(cv2.CAP_PROP_FPS)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total_frames / fps
                
                # Xác định thời điểm lấy frame
                if timestamp is None:
                    timestamp = duration / 2  # Giữa video
                elif timestamp > duration:
                    timestamp = duration * 0.8  # 80% video nếu timestamp quá lớn
                
                # Nhảy đến frame cần thiết
                frame_number = int(timestamp * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                
                # Đọc frame
                ret, frame = cap.read()
                if not ret:
                    raise ValueError("Không thể đọc frame từ video")
                
                # Tạo tên file
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"frame_{timestamp_str}_{uuid.uuid4().hex[:8]}.jpg"
                file_path = self.output_dir / filename
                
                # Lưu frame
                cv2.imwrite(str(file_path), frame)
                
                # Tạo URL
                url_path = f"/images/{filename}"
                
                logger.info(f"Đã trích xuất frame thành công: {file_path}")
                return str(file_path), url_path
                
            finally:
                cap.release()
                
        except Exception as e:
            logger.error(f"Lỗi trích xuất frame từ video local: {str(e)}")
            raise
    
    async def extract_frame_from_youtube(
        self, 
        youtube_url: str, 
        timestamp: Optional[float] = None
    ) -> Tuple[str, str]:
        """
        Trích xuất frame từ YouTube URL
        
        Args:
            youtube_url: URL video YouTube
            timestamp: Thời điểm lấy frame (giây), None = giữa video
            
        Returns:
            Tuple[file_path, url_path]: Đường dẫn file và URL
        """
        temp_video_path = None
        try:
            logger.info(f"Trích xuất frame từ YouTube: {youtube_url}")
            
            # Tạo tên file tạm thời
            temp_id = uuid.uuid4().hex[:8]
            
            # Cấu hình download
            ydl_opts = self.ydl_opts.copy()
            ydl_opts['outtmpl'] = str(self.output_dir / f'temp_{temp_id}.%(ext)s')
            
            # Download video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Lấy thông tin video trước
                info = ydl.extract_info(youtube_url, download=False)
                duration = info.get('duration', 0)
                
                # Xác định timestamp
                if timestamp is None:
                    timestamp = duration / 2  # Giữa video
                elif timestamp > duration:
                    timestamp = duration * 0.8  # 80% video
                
                # Download video
                ydl.download([youtube_url])
                
                # Tìm file đã download
                temp_files = list(self.output_dir.glob(f'temp_{temp_id}.*'))
                if not temp_files:
                    raise FileNotFoundError("Không tìm thấy file video đã download")
                
                temp_video_path = temp_files[0]
                
                # Trích xuất frame từ video đã download
                frame_path, url_path = await self.extract_frame_from_local_video(
                    str(temp_video_path), 
                    timestamp
                )
                
                logger.info(f"Đã trích xuất frame từ YouTube thành công: {frame_path}")
                return frame_path, url_path
                
        except Exception as e:
            logger.error(f"Lỗi trích xuất frame từ YouTube: {str(e)}")
            raise
            
        finally:
            # Xóa file video tạm thời
            if temp_video_path and os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                    logger.info(f"Đã xóa file tạm thời: {temp_video_path}")
                except Exception as e:
                    logger.warning(f"Không thể xóa file tạm thời: {e}")
    
    def validate_youtube_url(self, url: str) -> bool:
        """
        Kiểm tra URL YouTube hợp lệ
        """
        youtube_patterns = [
            'youtube.com/watch',
            'youtu.be/',
            'youtube.com/embed/',
            'm.youtube.com/watch'
        ]
        return any(pattern in url for pattern in youtube_patterns)
    
    def validate_video_file(self, file_path: str) -> bool:
        """
        Kiểm tra file video hợp lệ
        """
        if not os.path.exists(file_path):
            return False
        
        # Kiểm tra extension
        valid_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
        file_ext = os.path.splitext(file_path)[1].lower()
        
        return file_ext in valid_extensions
    
    async def get_video_info(self, youtube_url: str) -> dict:
        """
        Lấy thông tin video YouTube
        """
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0)
                }
        except Exception as e:
            logger.error(f"Lỗi lấy thông tin video: {str(e)}")
            return {}


# Singleton instance
video_extractor = VideoFrameExtractor() 