import json
import os
import time
from pathlib import Path
from .config import DATA, TTL


def directory(job_id):
    return DATA / job_id


def write_json(path: Path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def status(job_id):
    path = directory(job_id) / 'status.json'
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if value['created_at'] + TTL < time.time():
        return None
    return value


def update(job_id, state, progress, message, **extra):
    path = directory(job_id) / 'status.json'
    previous = json.loads(path.read_text()) if path.exists() else {'created_at': time.time()}
    write_json(path, {**previous, 'state': state, 'progress': progress,
                      'message': message, 'updated_at': time.time(), **extra})
