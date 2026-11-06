import logging
import shutil
import time
from celery import Celery
from .config import REDIS_URL, DATA, TTL, JOB_TIMEOUT
from .store import directory, status, update

celery = Celery('stltostp', broker=REDIS_URL, backend=REDIS_URL)
celery.conf.update(task_track_started=True, worker_prefetch_multiplier=1,
                   task_serializer='json', accept_content=['json'], result_serializer='json',
                   task_soft_time_limit=JOB_TIMEOUT-20, task_time_limit=JOB_TIMEOUT,
                   result_expires=TTL, broker_connection_retry_on_startup=True,
                   beat_schedule={'cleanup-hourly': {'task': 'cleanup', 'schedule': 3600.0}})


@celery.task(name='convert_job')
def convert_job(job_id, unit, merge_planes, curve_mode='off', fit_tolerance=.05, max_volume_change=.02,
                simplify_mesh=False, target_faces=None, simplify_tolerance=.05):
    from .geometry import convert
    if status(job_id) is None:
        return
    update(job_id, 'running', 5, 'Đã nhận tác vụ')
    try:
        report = convert(directory(job_id) / 'source.stl', directory(job_id), unit, merge_planes,
                         lambda p, m: update(job_id, 'running', p, m), curve_mode=curve_mode,
                         fit_tolerance=fit_tolerance, max_volume_change=max_volume_change,
                         simplify_mesh=simplify_mesh, target_faces=target_faces,
                         simplify_tolerance=simplify_tolerance)
        update(job_id, 'completed' if report['success'] else 'failed', 100,
               'Đã xác minh STEP' if report['success'] else report.get('error', 'Chuyển đổi thất bại'))
    except Exception:
        logging.exception('Conversion failed: %s', job_id)
        update(job_id, 'failed', 100, 'Worker gặp lỗi hoặc vượt thời gian xử lý. Vui lòng thử lưới nhỏ hơn.')


@celery.task(name='cleanup')
def cleanup():
    DATA.mkdir(parents=True, exist_ok=True)
    deleted = 0
    for folder in DATA.iterdir():
        if not folder.is_dir():
            continue
        import json
        try:
            metadata = json.loads((folder / 'status.json').read_text())
            created = metadata['created_at']
        except (OSError, ValueError, KeyError):
            created = folder.stat().st_mtime
        if created + TTL < time.time():
            shutil.rmtree(folder)
            deleted += 1
    return deleted
