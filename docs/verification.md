# Kết quả kiểm thử bản đầu

Kiểm thử thực hiện ngày 2026-11-05.

## Đã kiểm tra trong môi trường phát triển

- 17 kiểm thử Python thành công, dùng OCCT 7.8.1.1 qua `cadquery-ocp`.
- Khối hộp 20 × 30 × 12: 12 tam giác đầu vào → 6 mặt B-rep; 1 solid hợp lệ, thể tích 7.200 đơn vị khối.
- Các đơn vị mm/cm/m/inch: kiểm tra số tọa độ sau round-trip và dùng một reader độc lập đọc sang mm để đối chiếu kích thước vật lý.
- Lưới hở: báo tọa độ cạnh lỗi, không có file STEP để tải.
- Mặt trùng và hướng mặt sai: sửa rồi xác minh lại.
- Hai khối rời nhau: giữ 2 solid; hai vùng bao chồng nhau: từ chối chuyển tự động.
- Lưới trụ 24 cạnh: gộp hai mặt đầu, giữ các mặt bên dạng faceted; không tuyên bố đã khớp mặt trụ.
- Chế độ không gộp mặt: hộp vẫn có 12 mặt tam giác.
- API key sai, token job sai, file rỗng, sai đuôi, lỗi queue, job hết hạn, dọn TTL: có kiểm thử.
- WebSocket gửi token trong frame đầu và trả trạng thái hoàn tất: có kiểm thử.
- Build production frontend thành công. Bundle chính khoảng 744 KB chưa nén, khoảng 202 KB gzip; còn có thể tối ưu tách Three.js.
- **Redis thật + Celery worker thật + FastAPI HTTP:** tải khối hộp, xử lý nền, polling, tải STEP và đọc báo cáo thành công. STEP nhận được 16.220 byte, 6 mặt, thể tích 7.200.

## Chưa xác minh tại thời điểm viết

- Giao diện trực quan và thao tác WebGL trên trình duyệt: trình duyệt của môi trường này không truy cập được cổng local của ứng dụng.
- Toàn stack Docker tại máy phát triển: không có Docker Engine; workflow GitHub thực hiện build và smoke test riêng. Xem trạng thái Actions để biết kết quả container.
- Lưới công nghiệp lớn và file của người dùng; chưa benchmark giới hạn 30.000 mặt/4 GB RAM.
- Tự giao đầy đủ, sai lệch bề mặt hai chiều, phục dựng mặt trụ/cầu/NURBS, AI, MinIO/S3 và chạy nhiều VPS.
- Chưa có máy chủ đích/domain được cung cấp nên chưa có URL website chạy production.
