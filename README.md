# FORMSHIFT · STL to STEP

Công cụ web chuyển STL sang solid B-rep và STEP, có báo cáo lỗi hình học và kiểm tra lại file sau xuất. Repo: `pipipepea/STLTOSTP`.

## Bản 0.3 làm được gì?

- Tải STL ASCII/binary, xem 3D bằng Three.js; parse trong Web Worker.
- Giảm lưới theo tùy chọn trước khi dựng CAD, có giới hạn sai lệch, thể tích và kiểm tra topology/cạnh sắc; tải STL đã giảm riêng, giữ nguyên nguồn.
- FastAPI nhận file, trả `task_id`; Celery + Redis xử lý nền. Tiến độ qua WebSocket, có polling dự phòng.
- Phát hiện cạnh hở, cạnh phi đa tạp, mặt trùng, mặt suy biến và ghi tọa độ vùng bao lỗi vào JSON.
- Chỉ hàn các đỉnh có tọa độ bằng nhau chính xác; loại mặt trùng/suy biến và sửa hướng mặt. Không tự vá lỗ hoặc làm mịn.
- OCCT dựng shell/solid thật. Tùy chọn gộp mặt đồng phẳng: khối hộp 12 tam giác được chuyển thành 6 mặt B-rep.
- **Phục dựng bề mặt cong:** cầu, xuyến và biên dạng tròn xoay tạo mặt trụ/nón chuẩn; hỗ trợ ống rỗng, trục bậc và cạnh vát đồng tâm. Khối đùn sâu không đổi có lỗ tròn lệch tâm hoặc đường bao bo tròn có thể dựng lại các mặt trụ cục bộ.
- Dung sai theo đơn vị nguồn, giới hạn thay đổi thể tích, đo sai lệch hai chiều, kiểm tra topology Euler và giữ các góc của biên dạng tròn xoay. Đếm loại mặt CAD thật sau khi đọc STEP, không chỉ đếm tam giác xem trước.
- Kiểm tra B-rep, thể tích dương, số solid, kích thước bao; xuất STEP AP214, nhập lại và đối chiếu số solid/thể tích/kích thước.
- Tải STEP, STL đã sửa và báo cáo JSON. Bản xem đầu ra được tessellate từ STEP đã nhập lại.
- File bị từ chối truy cập sau 24 giờ; Celery Beat dọn file trong lần chạy hàng giờ kế tiếp (thời gian lưu vật lý có thể tới 25 giờ). Không lưu file người dùng vào Git.

**Phạm vi hình học:** fitting hình học có kiểm chứng, chưa dùng AI. Chỉ thay các thành phần/biên dạng thuộc nhóm được hỗ trợ và đạt dung sai; các vùng còn lại giữ mặt tam giác. Chưa khớp NURBS tự do, mọi fillet/loft hoặc lỗ xiên/độ sâu thay đổi. Sai lệch bề mặt là số đo lấy mẫu, không phải bảo đảm Hausdorff liên tục. Mesh self-intersection chưa được kiểm tra đầy đủ; BRepCheck không thay thế mọi kiểm tra tự giao. Chưa chứng nhận dùng trực tiếp cho sản xuất.

## Lưới vượt 30.000 mặt: giảm trước khi chuyển

1. Bật **Giảm lưới trước chuyển đổi**. Mặc định không bật để không tự thay đổi hình dạng.
2. Với lưới 45.844 mặt, có thể bắt đầu với **25.000 mặt đích**, dung sai **0.05 nếu đơn vị là mm**. Không bảo đảm file cụ thể đạt mục tiêu trước khi chạy kiểm tra.
3. Chuyển đổi, xem báo cáo giảm lưới và tải **STL đã giảm lưới** hoặc STEP. Nếu không đạt dung sai/topology/cạnh sắc, hệ thống dừng; hãy thử số mặt đích cao hơn (tối đa giới hạn CAD) thay vì ép giảm mạnh.

Mặc định đọc tối đa **200.000 mặt nguồn**, vẫn giới hạn **30.000 mặt đưa vào CAD** và 30 MB tải lên. Giảm lưới dùng VTK QuadricDecimation với volume preservation; kết quả phải kín, có cùng số thành phần và Euler, thay đổi thể tích mỗi thành phần không quá 1%, đạt kiểm tra cạnh sắc từ 30° và sai lệch hai chiều lấy mẫu. Thành phần nhỏ không quá 128 mặt được giữ nguyên. Đây không phải chứng nhận bảo toàn mọi chi tiết hay kiểm tra tự giao đầy đủ.

Dung sai giảm lưới và dung sai phục dựng cong là **hai bước riêng**: nếu đều là 0.05 mm, ngân sách cộng là 0.10 mm, cộng dung sai tessellation khi đo bản xem STEP. STEP cuối được đo bổ sung so với lưới gốc đã sửa, không chỉ so với lưới đã giảm. Số đo lấy mẫu chưa phải cận sai lệch liên tục.

API có thêm `simplify_mesh` (mặc định `false`), `target_faces` (mặc định `min(25000, MAX_FACES)`), `simplify_tolerance` (mặc định `0.05` đơn vị nguồn). `/api/config` trả giới hạn thực để giao diện cập nhật. Báo cáo có `simplification`, `conversion_mesh` và `verification.original_surface_deviation`.

## Dùng phục dựng bề mặt cong

1. Tải STL hoặc nhấn **Thử trụ R5 × H12**. Chọn đúng đơn vị.
2. Trong **Bề mặt cong · nâng cao**, chọn `Tự động`, nhập dung sai (mặc định `0.05` đơn vị nguồn), giới hạn thay đổi thể tích (mặc định `2%`). Không dùng dung sai lớn để ép nhận dạng; engine từ chối khớp nếu dung sai vượt 1% đường chéo thành phần.
3. Sau xử lý, xem từng thành phần: đã phục dựng hay giữ mặt gốc, loại bề mặt, sai lệch lấy mẫu hai chiều và Δ thể tích.
4. Tải STEP và báo cáo JSON. Báo cáo chứa trục, bán kính, biên dạng, lỗ, thử khớp bị từ chối và tọa độ sai lệch lớn nhất.

| Chế độ | Hành vi |
|---|---|
| Tự động (`auto`) | Thay thành phần đạt kiểm tra; giữ B-rep faceted cho phần không đạt và báo rõ |
| Bắt buộc (`required`) | Không xuất STEP nếu bất kỳ thành phần nào không khớp được, kể cả khối hộp thuần phẳng |
| Tắt (`off`) | Giữ luồng gộp mặt phẳng của bản 0.1 |

Giao diện mặc định `auto`. API mặc định `off` để tương thích client cũ; các trường form mới là `curve_mode`, `fit_tolerance`, `max_volume_change` (tỷ lệ, ví dụ `0.02` là 2%, tối đa `0.05`). Dung sai là đơn vị nguồn, không tự chuyển giá trị khi đổi lựa chọn đơn vị trên giao diện.

## Chạy trên VPS bằng Docker

Yêu cầu Docker Engine + Compose v2; khởi đầu nên dùng máy có khoảng 4 CPU, 8 GB RAM và đủ dung lượng lưu file. Không yêu cầu GPU cho bản hiện tại.

```bash
git clone https://github.com/pipipepea/STLTOSTP.git
cd STLTOSTP
cp .env.example .env
python3 scripts/setup_env.py
docker compose up -d --build
docker compose ps
```

Mở `http://localhost:8080` trên VPS, hoặc tạo SSH tunnel từ máy cá nhân:

```bash
ssh -L 8080:127.0.0.1:8080 user@YOUR_VPS
```

Mở `http://localhost:8080` ở máy cá nhân. Nhấn **Kết nối máy chủ**, nhập `API_KEY` trong `.env`, rồi thử khối mẫu. Khóa chỉ nằm trong bộ nhớ trang, không đưa vào frontend build hoặc Git.

Compose chỉ bind cổng web vào `127.0.0.1`; Redis và API không mở cổng ra ngoài. Muốn mở cho người khác sử dụng, đặt reverse proxy HTTPS, xác thực người dùng, giới hạn tần suất và dung lượng theo tài khoản trước khi mở truy cập. API key dùng chung của bản đầu dành cho một nhóm tin cậy; chưa có phân quyền nhiều người dùng hay giới hạn tổng dung lượng hàng đợi. File và Redis dùng Docker volume của một máy; chưa hỗ trợ worker trên nhiều máy.

```bash
docker compose logs -f worker
docker compose logs --tail=100 api
docker compose down
```

Không thêm `-v` vào lệnh `down` nếu cần giữ dữ liệu hiện tại.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `API_KEY` | bắt buộc | Khóa ngẫu nhiên ít nhất 24 ký tự |
| `HTTP_PORT` | 8080 | Cổng loopback của web |
| `MAX_UPLOAD_MB` | 30 | Giới hạn tải lên của API; frontend/Nginx mặc định 30/31 MB |
| `MAX_FACES` | 30000 | Giới hạn lưới đưa vào CAD sau giảm |
| `MAX_INPUT_FACES` | 200000 | Giới hạn số mặt đọc từ STL nguồn |
| `RETENTION_HOURS` | 24 | Thời gian hết hạn truy cập file |
| `JOB_TIMEOUT_SECONDS` | 900 | Giới hạn xử lý mỗi job; phải lớn hơn 20 |

STL không lưu đơn vị: phải chọn đúng `mm`, `cm`, `m`, hoặc `inch`. Tọa độ số của STL không bị scale trong file nguồn; STEP được gán đơn vị tương ứng. Báo cáo ghi kích thước/thể tích theo đơn vị nguồn và lũy thừa của đơn vị đó.

Nếu có nhiều thành phần, chỉ chấp nhận những khối có vùng bao không chồng nhau. Khối lồng nhau/lòng rỗng và assembly có vùng bao giao nhau cần xử lý riêng. Lưới hở bị từ chối xuất STEP nhưng vẫn có báo cáo vị trí lỗi.

## Phát triển và kiểm thử

Python 3.12 và Node.js 22.12+:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
python -m pytest -q
cd ../frontend
npm ci
npm run build
```

Chạy API/worker ngoài Docker cần Redis và cùng `DATA_DIR`, `REDIS_URL`, `API_KEY`. Chạy worker bằng `python -m celery -A app.tasks.celery worker --concurrency=1`; khởi động API bằng `python -m uvicorn app.main:app --port 8000`. `npm run dev` proxy `/api` tới `127.0.0.1:8000`. Chạy scheduler bằng `python -m celery -A app.tasks.celery beat --schedule=/tmp/stltostp-beat` để dọn file.

API tests chạy conversion thật với OCCT, nhưng thay queue dispatch bằng thực thi đồng bộ để không cần Redis. `scripts/smoke_test.py` kiểm tra API và worker bất đồng bộ khi stack đang chạy.

## Kiến trúc và giai đoạn kế tiếp

Xem [docs/curved-surfaces.md](docs/curved-surfaces.md), [docs/architecture.md](docs/architecture.md) và [docs/deployment.md](docs/deployment.md). GPU inference, NURBS tự do, MinIO/S3, CAD self-intersection kiểm tra nâng cao và auth nhiều người dùng nằm trong roadmap, chưa là tính năng hoạt động.
