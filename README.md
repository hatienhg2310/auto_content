# YouTube Content Automation System

Hệ thống tự động hóa tạo nội dung YouTube với AI - Multi Channel Support

## Tính năng

- Tạo nội dung tự động cho nhiều kênh YouTube khác nhau
- Sử dụng thông tin kênh (tên kênh, mô tả kênh) để tạo tiêu đề và mô tả video phù hợp
- Tạo thumbnail tự động với AI
- Hỗ trợ nhiều chủ đề nội dung khác nhau
- API đầy đủ để tích hợp với các hệ thống khác

## Cài đặt

1. Clone repository:

```
git clone https://github.com/yourusername/auto_content.git
cd auto_content
```

2. Cài đặt các thư viện phụ thuộc:

```
pip install -r requirements.txt
```

3. Tạo file cấu hình:

```
cp config/settings_example.py config/settings.py
```

4. Chỉnh sửa file cấu hình `config/settings.py` với thông tin API key của bạn

## Sử dụng

### Chạy demo tạo nội dung

```
python demo_generate_content.py
```

Demo này sẽ:
- Tạo một kênh demo nếu chưa tồn tại
- Tạo nội dung với chủ đề cụ thể
- Tạo nội dung dựa hoàn toàn vào thông tin kênh

### Chạy API server

```
python -m src.main
```

API server sẽ chạy tại địa chỉ http://localhost:8000

### Sử dụng API demo

```
python api_demo.py
```

API demo sẽ:
- Tạo một kênh mới thông qua API
- Tạo nội dung với chủ đề cụ thể
- Tạo nội dung dựa hoàn toàn vào thông tin kênh
- Tạo nhiều nội dung cùng lúc
- Lấy danh sách packages và chi tiết package

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

## Cấu trúc dự án

```
auto_content/
  - config/
    - settings.py          # Cấu hình hệ thống
  - data/                  # Thư mục lưu dữ liệu
  - logs/                  # Thư mục lưu logs
  - src/
    - ai_service.py        # Dịch vụ tạo nội dung AI
    - channel_manager.py   # Quản lý kênh
    - image_service.py     # Dịch vụ tạo ảnh
    - main.py              # API server
    - models.py            # Các model dữ liệu
    - workflow_engine.py   # Engine điều phối workflow
  - static/                # Tài nguyên tĩnh
  - templates/             # Templates HTML
  - demo_generate_content.py # Demo tạo nội dung
  - api_demo.py            # Demo sử dụng API
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

## Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng tạo issue hoặc pull request.

## Giấy phép

MIT License 