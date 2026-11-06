import os
from pathlib import Path

DATA = Path(os.getenv('DATA_DIR', '/data'))
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
API_KEY = os.getenv('API_KEY', '')
MAX_UPLOAD = int(os.getenv('MAX_UPLOAD_MB', '30')) * 1024 * 1024
MAX_FACES = int(os.getenv('MAX_FACES', '30000'))
MAX_INPUT_FACES = int(os.getenv('MAX_INPUT_FACES', '200000'))
TTL = int(os.getenv('RETENTION_HOURS', '24')) * 3600
JOB_TIMEOUT = int(os.getenv('JOB_TIMEOUT_SECONDS', '900'))
