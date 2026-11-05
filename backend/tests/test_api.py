import os
import tempfile
from pathlib import Path

# Isolated data and explicit API key; never touch deployed job storage.
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stltostp-tests-')
os.environ['API_KEY'] = 'test-only-key-with-more-than-24-characters'

import numpy as np
import pytest
import trimesh
from fastapi.testclient import TestClient
from app.main import app
from app.tasks import convert_job, cleanup
from app.store import directory, update, write_json, status
from app.config import API_KEY, TTL


@pytest.fixture
def client(monkeypatch):
    def execute(args, **kwargs):
        return convert_job.run(*args)
    monkeypatch.setattr(convert_job, 'apply_async', execute)
    with TestClient(app) as test:
        yield test


def submit(client, mesh=None):
    mesh = mesh if mesh is not None else trimesh.creation.box()
    response = client.post('/api/jobs', headers={'X-API-Key': API_KEY},
                           files={'file': ('cube.stl', mesh.export(file_type='stl'), 'model/stl')})
    assert response.status_code == 202, response.text
    job = response.json()
    return job, {'X-Job-Token': job['token']}


def test_full_upload_convert_status_download(client):
    job, headers = submit(client)
    url = '/api/jobs/' + job['task_id']
    response = client.get(url, headers=headers)
    assert response.json()['state'] == 'completed'
    assert 'token' not in response.json()
    assert client.get(url).status_code == 404
    assert client.get(url, headers={'X-Job-Token': 'wrong'}).status_code == 404
    step = client.get(url+'/files/step', headers=headers)
    assert step.status_code == 200
    assert step.content.startswith(b'ISO-10303-21;')
    assert client.get(url+'/files/preview', headers=headers).status_code == 200
    report = client.get(url+'/files/report', headers=headers).json()
    assert report['verification']['after_reimport']['faces'] == 6
    with client.websocket_connect(url+'/events') as ws:
        ws.send_json({'token': job['token']})
        assert ws.receive_json()['state'] == 'completed'


def test_failure_keeps_report_but_never_offers_step(client):
    mesh = trimesh.creation.box()
    mesh.update_faces(np.arange(11))
    job, headers = submit(client, mesh)
    url = '/api/jobs/'+job['task_id']
    assert client.get(url, headers=headers).json()['state'] == 'failed'
    assert client.get(url+'/files/step', headers=headers).status_code == 409
    assert client.get(url+'/files/report', headers=headers).status_code == 200


def test_reject_bad_auth_empty_file_and_extension(client):
    assert client.post('/api/jobs', files={'file': ('a.stl', b'abc')}).status_code == 401
    h = {'X-API-Key': API_KEY}
    assert client.post('/api/jobs', files={'file': ('a.stl', b'')}, headers=h).status_code == 422
    assert client.post('/api/jobs', files={'file': ('a.exe', b'abc')}, headers=h).status_code == 422


def test_expired_job_inaccessible_and_cleanup_removes_it(client):
    import time
    job, headers = submit(client)
    folder = directory(job['task_id'])
    value = status(job['task_id'])
    value['created_at'] = time.time() - TTL - 1
    write_json(folder/'status.json', value)
    assert client.get('/api/jobs/'+job['task_id'], headers=headers).status_code == 404
    assert cleanup.run() >= 1
    assert not folder.exists()


def test_queue_failure_returns_service_unavailable(client, monkeypatch):
    def offline(**kwargs):
        raise ConnectionError('offline')
    monkeypatch.setattr(convert_job, 'apply_async', offline)
    h = {'X-API-Key': API_KEY}
    response = client.post('/api/jobs', headers=h, files={'file': ('a.stl', b'abc')})
    assert response.status_code == 503
