# Cập nhật bản Windows đã tải ZIP

Mở PowerShell tại thư mục đang dùng, nơi có `compose.yaml` và `.env`. Đảm bảo Docker Desktop đang chạy. Đoạn lệnh dưới tải mã nguồn mới từ repo, giữ `.env` hiện tại và giữ các Docker volume; không tạo khóa API mới.

```powershell
$zip = Join-Path $env:TEMP "stltostp-update.zip"
$destination = Join-Path $env:TEMP ("stltostp-update-" + [guid]::NewGuid().ToString("N"))
Invoke-WebRequest -Uri "https://github.com/pipipepea/STLTOSTP/archive/refs/heads/main.zip" -OutFile $zip
Expand-Archive -Path $zip -DestinationPath $destination
Copy-Item -Path (Join-Path $destination "STLTOSTP-main\*") -Destination . -Recurse -Force
docker compose up -d --build
```

Chờ hoàn tất, mở `http://localhost:8080` và nhấn Ctrl+F5 để tải giao diện mới. Kiểm tra phiên bản `v0.3` và mục **Giảm lưới · tùy chọn**. Với STL 45.844 mặt, thử số mặt đích 25.000 và dung sai 0.05 nếu đơn vị nguồn là mm; không tăng dung sai chỉ để buộc chuyển thành công.

Nếu chỉ chép lại mã nguồn nhưng chưa chạy build, container vẫn dùng mã cũ. Không ghi đè `.env` bằng khóa mới. Không dùng `docker compose down -v` để cập nhật vì sẽ xóa volume dữ liệu.

Với bản clone bằng Git, thay bước tải/chép ZIP bằng `git pull --ff-only`, rồi chạy `docker compose up -d --build`.
