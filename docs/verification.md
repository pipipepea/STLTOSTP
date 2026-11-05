# Kết quả kiểm thử v0.2

Kiểm thử thực hiện ngày 2026-11-05.

## Đã kiểm tra trong môi trường phát triển

- **46 kiểm thử Python thành công** trong môi trường phát triển, dùng OCCT 7.8.1.1 qua `cadquery-ocp`, gồm các kiểm thử 0.1 và phục dựng cong bên dưới. Kết quả chạy container được ghi trong GitHub Actions.
- Khối hộp 20 × 30 × 12: 12 tam giác đầu vào → 6 mặt B-rep; 1 solid hợp lệ, thể tích 7.200 đơn vị khối.
- Các đơn vị mm/cm/m/inch: kiểm tra số tọa độ sau round-trip và dùng một reader độc lập đọc sang mm để đối chiếu kích thước vật lý.
- Lưới hở: báo tọa độ cạnh lỗi, không có file STEP để tải.
- Mặt trùng và hướng mặt sai: sửa rồi xác minh lại.
- Hai khối rời nhau: giữ 2 solid; hai vùng bao chồng nhau: từ chối chuyển tự động.
- Khi `curve_mode=off`, trụ 24 cạnh vẫn giữ mặt bên faceted như 0.1.
- Trụ, nón, cầu, xuyến: tạo các mặt cylinder/cone/sphere/torus thật, kiểm tra loại mặt sau đọc STEP. Trụ R5 × H12 trở thành 2 mặt phẳng + 1 mặt trụ, thể tích CAD `300π`.
- Ống rỗng, trục bậc có vát: giữ lỗ, vai và cạnh vát qua các mặt phẳng/trụ/nón chuẩn.
- Tấm 20 × 16 × 4 có 2 lỗ tròn lệch tâm: từ 524 tam giác thành 6 mặt phẳng + 2 mặt trụ. Giữ cả 2 lỗ; kiểm tra trường hợp xoay/di chuyển trong không gian.
- Biên dạng chữ nhật bo 4 góc được đùn: 6 mặt phẳng + 4 mặt trụ góc. Tiết diện thay đổi theo độ sâu bị từ chối khớp và giữ faceted.
- Trụ xoay lệch trục/di chuyển: kiểm tra bán kính và hướng trục bằng reader độc lập. Kiểm tra đơn vị vật lý mm/cm/m/inch cho cả bề mặt cong.
- Dung sai quá chặt, giới hạn thể tích thấp, chi tiết bất đối xứng và assembly trộn dạng hỗ trợ/không hỗ trợ: kiểm tra fallback minh bạch; chế độ `required` không xuất STEP nếu không đạt.
- Kiểm tra riêng hướng CAD → mesh, tham số API tới worker và từ chối NaN/Infinity/giới hạn sai.
- Chế độ không gộp mặt: hộp vẫn có 12 mặt tam giác.
- API key sai, token job sai, file rỗng, sai đuôi, lỗi queue, job hết hạn, dọn TTL: có kiểm thử.
- WebSocket gửi token trong frame đầu và trả trạng thái hoàn tất: có kiểm thử.
- Build production frontend thành công. Còn có thể tối ưu bundle bằng tách Three.js.
- **Redis thật + Celery worker thật + FastAPI HTTP:** tải khối hộp, xử lý nền, polling, tải STEP và đọc báo cáo thành công. STEP nhận được 16.220 byte, 6 mặt, thể tích 7.200.
- Smoke test mới cũng chuyển trụ qua hàng đợi thật: STEP 5.776 byte, 3 mặt (2 phẳng + 1 trụ), thể tích khoảng 942,4778; phép đo tới shell STEP sau nhập lại nằm trong dung sai 0,05.

## Chưa xác minh tại thời điểm viết

- Giao diện trực quan và thao tác WebGL trên trình duyệt: trình duyệt của môi trường này không truy cập được cổng local của ứng dụng.
- Toàn stack Docker tại máy phát triển: không có Docker Engine; workflow GitHub thực hiện build và smoke test riêng. Xem trạng thái Actions để biết kết quả container.
- Lưới công nghiệp lớn và file của người dùng; chưa benchmark giới hạn 30.000 mặt/4 GB RAM.
- Tự giao đầy đủ, cận Hausdorff liên tục, NURBS tự do/mọi patch cục bộ, scan nhiễu lớn, AI, MinIO/S3 và chạy nhiều VPS.
- Chưa có máy chủ đích/domain được cung cấp nên chưa có URL website chạy production.
