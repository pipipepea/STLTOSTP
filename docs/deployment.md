# Vận hành trên VPS

## Trước khi mở truy cập

Chạy các bước README bằng SSH trên VPS có Docker/Compose. File `.env` chỉ tồn tại trên máy chủ và đã được `.gitignore` loại trừ. Không đưa API key vào Docker image, frontend build, URL hay GitHub Actions secrets trừ khi có nhu cầu triển khai cụ thể.

Mặc định `web` bind `127.0.0.1:8080`. Dùng SSH tunnel cho bản thử nghiệm. Muốn có URL công khai cần một máy chủ/domain cụ thể và reverse proxy TLS. GitHub lưu mã nguồn và chạy CI; GitHub Pages không chạy được Python/Celery/OCCT.

## Kiểm thử khi đã khởi động

```bash
docker compose ps
curl --fail http://127.0.0.1:8080/api/health
```

Chạy smoke test từ container API với key đã có trong môi trường container:

```bash
docker compose exec -T api python - <<'PY'
import os, time, urllib.request, json, uuid
boundary = uuid.uuid4().hex
verts = [(0,0,0),(1,0,0),(0,1,0),(0,0,1)]
faces = [(0,2,1),(0,1,3),(1,2,3),(2,0,3)]
stl = 'solid test\n' + '\n'.join('facet normal 0 0 0\nouter loop\n' + '\n'.join('vertex '+ ' '.join(map(str, verts[i])) for i in f) + '\nendloop\nendfacet' for f in faces) + '\nendsolid test'
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="test.stl"\r\nContent-Type: model/stl\r\n\r\n{stl}\r\n--{boundary}--\r\n').encode()
req = urllib.request.Request('http://localhost:8000/api/jobs', data=body, headers={'X-API-Key':os.environ['API_KEY'],'Content-Type':f'multipart/form-data; boundary={boundary}'})
job = json.load(urllib.request.urlopen(req))
for _ in range(120):
    req = urllib.request.Request('http://localhost:8000/api/jobs/'+job['task_id'], headers={'X-Job-Token':job['token']})
    state = json.load(urllib.request.urlopen(req))
    if state['state'] in ('completed','failed'):
        break
    time.sleep(1)
assert state['state'] == 'completed', state
print('Async conversion passed')
PY
```

Hoặc cài dependencies dev trên máy cá nhân, đặt `API_KEY` qua môi trường và chạy `scripts/smoke_test.py` như README. Smoke test không in API key hoặc token job.

## Giới hạn tài nguyên

Worker chạy concurrency 1, RAM tối đa 4 GB và 2 CPU; task soft timeout mặc định 880 giây, hard timeout 900 giây. Lưới rất nhiều mặt có thể tốn RAM lớn khi dựng B-rep; tăng giới hạn phải đi kèm benchmark và dung lượng RAM.

File lưu trong volume cục bộ: API, worker và scheduler phải chạy cùng máy và volume. Chưa có tổng quota hay cơ chế chống lạm dụng cho public SaaS. Redis không expose cổng ra host. `API_KEY` ngẫu nhiên chỉ thích hợp nhóm tin cậy.

## Nâng cấp

Pull commit đã kiểm thử, backup cấu hình nếu cần, rồi:

```bash
git pull --ff-only
docker compose up -d --build
docker compose logs --tail=80 worker api
```

Không sửa `.env.example` bằng key thật. Chạy `docker compose down` không xóa volume; `down -v` sẽ xóa dữ liệu. File đang xử lý có thể cần gửi lại sau nâng cấp.

## Hiện trạng kiểm thử

Các kiểm thử Python dùng OCCT thật; API tests thay dispatch queue bằng thực thi đồng bộ. Workflow GitHub bổ sung build Docker Compose, Redis thật, worker thật và smoke test HTTP bất đồng bộ. Xem trạng thái Actions cho kết quả môi trường container.
