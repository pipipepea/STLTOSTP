# FORMSHIFT · STL to STEP

Công cụ web chuyển STL sang solid B-rep và STEP, có báo cáo lỗi hình học và kiểm tra lại file sau xuất. Repo: `pipipepea/STLTOSTP`.

## Bản đầu làm được gì?

- Tải STL ASCII/binary, xem 3D bằng Three.js; parse trong Web Worker.
- FastAPI nhận file, trả `task_id`; Celery + Redis xử lý nền. Tiến độ qua WebSocket, có polling dự phòng.
- Phát hiện cạnh hở, cạnh phi đa tạp, mặt trùng, mặt suy biến và ghi tọa độ vùng bao lỗi vào JSON.
- Chỉ hàn các đỉnh có tọa độ bằng nhau chính xác; loại mặt trùng/suy biến và sửa hướng mặt. Không tự vá lỗ hoặc làm mịn.
- OCCT dựng shell/solid thật. Tùy chọn gộp mặt đồng phẳng: khối hộp 12 tam giác được chuyển thành 6 mặt B-rep.
- Kiểm tra B-rep, thể tích dương, số solid, kích thước bao; xuất STEP AP214, nhập lại và đối chiếu số solid/thể tích/kích thước.
- Tải STEP, STL đã sửa và báo cáo JSON. Bản xem đầu ra được tessellate từ STEP đã nhập lại.
- File bị từ chối truy cập sau 24 giờ; Celery Beat dọn file trong lần chạy hàng giờ kế tiếp (thời gian lưu vật lý có thể tới 25 giờ). Không lưu file người dùng vào Git.

**Phạm vi hình học:** gộp các mặt phẳng; các vùng cong vẫn gồm nhiều mặt phẳng nhỏ. Chưa phục dựng tự động mặt trụ/cầu/NURBS, chưa có AI. Không coi STEP nhiều mặt tam giác là STEP đã tái dựng bề mặt tham số. Mesh self-intersection chưa được kiểm tra đầy đủ; BRepCheck không thay thế mọi kiểm tra tự giao. Chưa chứng nhận dùng trực tiếp cho sản xuất.

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
| `MAX_FACES` | 30000 | Chặn lưới quá lớn trước khi dựng CAD |
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

Xem [docs/architecture.md](docs/architecture.md) và [docs/deployment.md](docs/deployment.md). GPU inference, primitive fitting, MinIO/S3, CAD self-intersection kiểm tra nâng cao và auth nhiều người dùng nằm trong roadmap, chưa là tính năng hoạt động.
