import asyncio
import hmac
import math
import json
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import FileResponse
from .config import API_KEY, DATA, MAX_UPLOAD, JOB_TIMEOUT
from .store import directory, status, update, write_json
from .tasks import celery, convert_job


@asynccontextmanager
async def lifespan(app):
    if len(API_KEY) < 24 or API_KEY == 'replace-with-a-random-secret-at-least-24-characters':
        raise RuntimeError('Set API_KEY to a random secret of at least 24 characters.')
    DATA.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title='STL to STP', version='0.2.0', lifespan=lifespan)


def require_key(x_api_key: Annotated[str | None, Header()] = None):
    if not API_KEY or not hmac.compare_digest(x_api_key or '', API_KEY):
        raise HTTPException(401, 'API key không hợp lệ.')


def get_job(job_id, token):
    value = status(str(job_id))
    if not value or not hmac.compare_digest(value.get('token', ''), token or ''):
        raise HTTPException(404, 'Tác vụ không tồn tại hoặc đã hết hạn.')
    # A hard-killed worker can leave stale running metadata. Surface this instead
    # of leaving the UI spinning forever. Queue time is included in this bound.
    if value['state'] in {'queued', 'running'} and time.time() - value['updated_at'] > JOB_TIMEOUT+60:
        update(str(job_id), 'failed', 100, 'Tác vụ quá hạn hoặc worker không phản hồi.')
        value = status(str(job_id))
    return value


def public_status(value):
    return {k: v for k, v in value.items() if k != 'token'}


@app.get('/api/health')
def health():
    try:
        with celery.connection() as connection:
            connection.ensure_connection(max_retries=0, timeout=2)
        return {'status': 'ok', 'queue': 'connected'}
    except Exception:
        raise HTTPException(503, 'Không kết nối được Redis.')


@app.post('/api/jobs', status_code=202, dependencies=[Depends(require_key)])
async def submit(file: Annotated[UploadFile, File()],
                 unit: Annotated[str, Form()] = 'mm',
                 merge_planes: Annotated[bool, Form()] = True,
                 curve_mode: Annotated[str, Form()] = 'off',
                 fit_tolerance: Annotated[float, Form()] = .05,
                 max_volume_change: Annotated[float, Form()] = .02):
    if unit not in {'mm', 'cm', 'm', 'inch'}:
        raise HTTPException(422, 'Đơn vị không được hỗ trợ.')
    if curve_mode not in {'off', 'auto', 'required'}:
        raise HTTPException(422, 'Chế độ phục dựng không hợp lệ.')
    if not math.isfinite(fit_tolerance) or fit_tolerance <= 0:
        raise HTTPException(422, 'Dung sai phải là số hữu hạn lớn hơn 0.')
    if not math.isfinite(max_volume_change) or not 0 < max_volume_change <= .05:
        raise HTTPException(422, 'Giới hạn thay đổi thể tích phải lớn hơn 0 và không quá 5%.')
    if not (file.filename or '').lower().endswith('.stl'):
        raise HTTPException(422, 'Chỉ nhận file .stl.')
    job_id = str(uuid4())
    folder = directory(job_id)
    folder.mkdir(parents=True)
    total = 0
    try:
        with (folder / 'source.stl').open('wb') as target:
            while chunk := await file.read(1024*1024):
                total += len(chunk)
                if total > MAX_UPLOAD:
                    raise HTTPException(413, 'File vượt giới hạn tải lên.')
                target.write(chunk)
        if not total:
            raise HTTPException(422, 'File rỗng.')
        token = secrets.token_urlsafe(32)
        update(job_id, 'queued', 0, 'Đang chờ worker', token=token,
               filename=(file.filename or 'source.stl').replace('\\', '/').split('/')[-1][:200],
               unit=unit, size_bytes=total, curve_mode=curve_mode, fit_tolerance=fit_tolerance,
               max_volume_change=max_volume_change)
        convert_job.apply_async(args=[job_id, unit, merge_planes, curve_mode, fit_tolerance, max_volume_change],
                                task_id=job_id, expires=JOB_TIMEOUT)
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(503, 'Không gửi được tác vụ đến hàng đợi. Vui lòng thử lại.')
    finally:
        await file.close()
    return {'task_id': job_id, 'token': token}


@app.get('/api/jobs/{job_id}')
def get_status(job_id: UUID, x_job_token: Annotated[str | None, Header()] = None):
    return public_status(get_job(job_id, x_job_token))


FILES = {'step': ('result.step', 'application/step'),
         'report': ('report.json', 'application/json'),
         'source': ('source.stl', 'model/stl'),
         'repaired': ('repaired.stl', 'model/stl'),
         'preview': ('preview.stl', 'model/stl')}


@app.get('/api/jobs/{job_id}/files/{kind}')
def download(job_id: UUID, kind: str, x_job_token: Annotated[str | None, Header()] = None):
    value = get_job(job_id, x_job_token)
    if kind not in FILES:
        raise HTTPException(404)
    if kind in {'step', 'preview'} and value['state'] != 'completed':
        raise HTTPException(409, 'STEP chưa được xác minh thành công.')
    name, mime = FILES[kind]
    path = directory(str(job_id)) / name
    if not path.exists():
        raise HTTPException(404, 'File chưa sẵn sàng.')
    return FileResponse(path, media_type=mime, filename=name, headers={'Cache-Control': 'no-store'})


@app.websocket('/api/jobs/{job_id}/events')
async def events(ws: WebSocket, job_id: UUID):
    await ws.accept()
    try:
        # Authenticate via first frame, so capability tokens never enter URLs.
        data = await asyncio.wait_for(ws.receive_json(), timeout=10)
        token = data.get('token', '')
        if not isinstance(token, str):
            await ws.close(code=1008)
            return
        previous = None
        for _ in range(JOB_TIMEOUT+120):
            try:
                value = get_job(job_id, token)
            except HTTPException:
                await ws.close(code=1008)
                return
            message = public_status(value)
            if message != previous:
                await ws.send_json(message)
                previous = message
            if value['state'] in {'completed', 'failed'}:
                break
            await asyncio.sleep(1)
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError):
        return
    finally:
        if ws.client_state.name == 'CONNECTED':
            await ws.close()
