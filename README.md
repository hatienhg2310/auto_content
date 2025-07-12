# YouTube Content Automation System

Hệ thống tự động hóa tạo nội dung YouTube với AI - Multi Channel Support

## Tính năng

- Tạo nội dung tự động cho nhiều kênh YouTube khác nhau
- Sử dụng thông tin kênh (tên kênh, mô tả kênh) để tạo tiêu đề và mô tả video phù hợp
- Tạo thumbnail tự động với AI (Midjourney/DALL-E)
- Hỗ trợ nhiều chủ đề nội dung khác nhau
- Tích hợp Google Sheets để lưu trữ dữ liệu
- Giao diện web quản lý và xem trước ảnh
- API đầy đủ để tích hợp với các hệ thống khác

## Cài đặt

### 1. Clone repository:

```bash
git clone https://github.com/yourusername/auto_content.git
cd auto_content
```

### 2. Cài đặt các thư viện phụ thuộc:

```bash
pip install -r requirements.txt
```

### 3. Cấu hình Environment Variables

Tạo file `.env` trong thư mục gốc của dự án:

```bash
cp .env.example .env
```

Hoặc tạo file `.env` mới với nội dung sau:

```env
# AI API Configuration - Gemini API (Primary)
GEMINI_API_KEY=your-gemini-api-key-here
OPENAI_API_KEY=sk-your-openai-api-key-here

# Midjourney API (Piapi.ai) - Để tạo ảnh chất lượng cao
PIAPI_API_KEY=your-piapi-api-key-here

# Google APIs - Để lưu dữ liệu vào Google Sheets
GOOGLE_CREDENTIALS_FILE=path/to/your/google-credentials.json
GOOGLE_SHEETS_ID=your-google-sheets-id-here

# Airtable (Tùy chọn)
AIRTABLE_API_KEY=your-airtable-api-key
AIRTABLE_BASE_ID=your-airtable-base-id
AIRTABLE_TABLE_NAME=Content

# YouTube API (Tùy chọn - cho tương lai)
YOUTUBE_API_KEY=your-youtube-api-key
YOUTUBE_CLIENT_SECRETS_FILE=path/to/youtube-client-secrets.json

# Application Settings
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=True

# Storage Paths
DATA_STORAGE_PATH=./data
IMAGES_STORAGE_PATH=./data/images
LOGS_PATH=./logs
```

### 4. Cấu hình Credentials

#### 4.1. Google Gemini API (Bắt buộc)

1. Truy cập [Google AI Studio](https://aistudio.google.com/)
2. Tạo API key mới
3. Copy API key và paste vào `GEMINI_API_KEY` trong file `.env`

#### 4.2. Piapi.ai (Midjourney API) - Để tạo ảnh

1. Truy cập [Piapi.ai](https://piapi.ai/)
2. Đăng ký tài khoản và mua credits
3. Lấy API key từ dashboard
4. Copy API key và paste vào `PIAPI_API_KEY` trong file `.env`

#### 4.3. Google Sheets Integration

1. Truy cập [Google Cloud Console](https://console.cloud.google.com/)
2. Tạo project mới hoặc chọn project có sẵn
3. Enable Google Sheets API
4. Tạo Service Account:
   - Vào IAM & Admin > Service Accounts
   - Tạo service account mới
   - Download JSON credentials file
   - Đặt file vào `src/credentials.json`
   - Cập nhật đường dẫn trong `GOOGLE_CREDENTIALS_FILE`

5. Tạo Google Sheets:
   - Tạo Google Sheets mới
   - Share sheet với email của service account (với quyền Editor)
   - Copy Sheet ID từ URL và paste vào `GOOGLE_SHEETS_ID`

#### 4.4. OpenAI API (Tùy chọn - Fallback)

1. Truy cập [OpenAI Platform](https://platform.openai.com/)
2. Tạo API key mới
3. Copy API key và paste vào `OPENAI_API_KEY` trong file `.env`

### 5. Cấu hình Google Sheets Format

Tạo header trong Google Sheets của bạn:

```
A: STT | B: Ảnh gen title | C: Title Video | D: Tên Thumb | E: Description | F: Tags | G: Ảnh Thumb | H: Ảnh Select | I: Package ID
```

### 6. Tạo file cấu hình kênh (Tùy chọn)

Chỉnh sửa file `channel_mapping_config.json` để cấu hình các kênh:

```json
{
  "channels": {
    "your-channel-id": {
      "channel_name": "Tên Kênh",
      "google_sheets_id": "your-specific-sheet-id",
      "google_sheet_gid": "0"
    }
  }
}
```

## Chạy ứng dụng

### Chạy Web Interface

```bash
python run.py
```

Truy cập: http://localhost:8000

### Chạy API Server

```bash
python -m src.main
```

API Documentation: http://localhost:8000/docs

### Chạy Demo

```bash
# Demo tạo nội dung
python demo_generate_content.py

# Demo API
python api_demo.py
```

## API Endpoints

### Quản lý kênh

- `POST /api/channels` - Tạo kênh mới
- `GET /api/channels` - Lấy danh sách kênh
- `GET /api/channels/{channel_id}` - Lấy thông tin kênh
- `PUT /api/channels/{channel_id}` - Cập nhật kênh
- `DELETE /api/channels/{channel_id}` - Xóa kênh

### Tạo nội dung

- `POST /api/create-content` - Tạo nội dung mới
- `POST /api/channels/{channel_id}/batch-create` - Tạo nhiều nội dung cùng lúc

### Quản lý packages

- `GET /api/packages/{package_id}` - Lấy chi tiết package
- `GET /api/channels/{channel_id}/packages` - Lấy danh sách packages của kênh
- `GET /api/packages` - Lấy tất cả packages
- `POST /api/cleanup` - Dọn dẹp packages cũ

### Quản lý ảnh

- `POST /api/packages/{package_id}/select-image` - Chọn ảnh từ 4 ảnh Midjourney

## Hướng dẫn sử dụng

### 1. Tạo nội dung qua Web Interface

1. Truy cập http://localhost:8000
2. Điền thông tin kênh và chủ đề video
3. Nhấn "Tạo Nội Dung"
4. Chờ hệ thống tạo content và ảnh
5. Vào Dashboard để xem kết quả
6. Click "Chi tiết" để xem 4 ảnh được tạo
7. Click vào ảnh muốn chọn làm thumbnail chính
8. Ảnh được chọn sẽ tự động lưu vào Google Sheets

### 2. Tạo nội dung qua API

```python
import requests

# Tạo nội dung mới
response = requests.post("http://localhost:8000/api/create-content", data={
    "channel_name": "Kênh Tech",
    "channel_description": "Kênh chia sẻ kiến thức công nghệ",
    "video_topic": "Hướng dẫn Python cơ bản",
    "additional_context": "Dành cho người mới bắt đầu"
})

print(response.json())
```

### 3. Tích hợp với Google Sheets

Sau khi tạo nội dung, dữ liệu sẽ tự động được lưu vào Google Sheets với format:

| STT | Ảnh gen title | Title Video | Tên Thumb | Description | Tags | Ảnh Thumb | Ảnh Select | Package ID |
|-----|---------------|-------------|-----------|-------------|------|-----------|------------|------------|
| 1   | url1\|url2\|url3\|url4 | Video Title | thumb.jpg | Video description | tag1,tag2 | url1\|url2\|url3\|url4 | url2 | pkg_001 |

## Troubleshooting

### Lỗi thường gặp

#### 1. "Gemini API key not found"
```
Giải pháp: Kiểm tra file .env và đảm bảo GEMINI_API_KEY được cấu hình đúng
```

#### 2. "Google Sheets permission denied"
```
Giải pháp: 
- Kiểm tra file credentials.json có đúng đường dẫn
- Đảm bảo service account có quyền Editor trên Google Sheets
- Kiểm tra GOOGLE_SHEETS_ID có đúng không
```

#### 3. "Piapi API error"
```
Giải pháp:
- Kiểm tra PIAPI_API_KEY có đúng không
- Đảm bảo tài khoản Piapi có đủ credits
- Kiểm tra kết nối internet
```

#### 4. "Package not found"
```
Giải pháp:
- Packages chỉ tồn tại trong bộ nhớ, sẽ mất khi restart server
- Kiểm tra logs để xem package có được tạo thành công không
```

### Logs và Debug

Kiểm tra logs tại thư mục `./logs/app.log`:

```bash
tail -f logs/app.log
```

Bật debug mode trong file `.env`:

```env
DEBUG=True
```

## Cấu trúc dự án

```
auto_content/
├── config/
│   └── settings.py          # Cấu hình hệ thống
├── data/                    # Thư mục lưu dữ liệu
├── logs/                    # Thư mục lưu logs
├── src/
│   ├── ai_service.py        # Dịch vụ tạo nội dung AI
│   ├── channel_manager.py   # Quản lý kênh
│   ├── database_service.py  # Dịch vụ lưu trữ database
│   ├── image_service.py     # Dịch vụ tạo ảnh
│   ├── main.py              # API server
│   ├── models.py            # Các model dữ liệu
│   └── workflow_engine.py   # Engine điều phối workflow
├── static/                  # Tài nguyên tĩnh
├── templates/               # Templates HTML
├── .env                     # Biến môi trường
├── .env.example            # Mẫu biến môi trường
├── requirements.txt        # Dependencies
└── run.py                  # Entry point
```

## Cách sử dụng thông tin kênh để tạo nội dung

Hệ thống sử dụng thông tin kênh (tên kênh, mô tả kênh) để tạo tiêu đề và mô tả video phù hợp. Khi tạo nội dung, hệ thống sẽ:

1. Lấy thông tin kênh từ `ChannelConfig`
2. Bổ sung thông tin vào `InputData`
3. Sử dụng AI để tạo nội dung phù hợp với kênh

Ví dụ:

```python
# Tạo kênh
channel = ChannelConfig(
    channel_id="my_channel",
    channel_name="My Channel",
    channel_description="Kênh chia sẻ kiến thức về công nghệ và lập trình",
    content_style="Giáo dục và giải trí",
    target_audience="Người Việt Nam 18-35 tuổi",
    content_topics=["Technology", "Programming", "AI"]
)

# Tạo input data
input_data = InputData(
    channel_id="my_channel",
    video_topic="Hướng dẫn sử dụng Python"
)

# Chạy workflow
package = await workflow_engine.run_full_workflow(input_data)

# Kết quả
print(package.generated_content.title)
print(package.generated_content.description)
```

