"""Run against a running stack: API_KEY=... python scripts/smoke_test.py [URL]."""
import json
import os
import sys
import time
import httpx
import trimesh

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080'
key = os.environ['API_KEY']
with httpx.Client(base_url=base, timeout=30, trust_env=False) as client:
    client.get('/api/health').raise_for_status()
    mesh = trimesh.creation.box(extents=[20, 30, 12])
    response = client.post('/api/jobs', headers={'X-API-Key': key},
                           files={'file': ('smoke.stl', mesh.export(file_type='stl'))})
    response.raise_for_status()
    job = response.json()
    headers = {'X-Job-Token': job['token']}
    for _ in range(120):
        response = client.get('/api/jobs/'+job['task_id'], headers=headers)
        response.raise_for_status()
        value = response.json()
        if value['state'] in ('completed', 'failed'):
            break
        time.sleep(1)
    assert value['state'] == 'completed', value
    step = client.get(f"/api/jobs/{job['task_id']}/files/step", headers=headers)
    step.raise_for_status()
    assert step.content.startswith(b'ISO-10303-21;')
    report = client.get(f"/api/jobs/{job['task_id']}/files/report", headers=headers).json()
    result = report['verification']['after_reimport']
    assert result['faces'] == 6 and result['solids'] == 1
    print(json.dumps({'state': value['state'], 'faces': result['faces'], 'volume': result['volume'],
                      'step_bytes': len(step.content)}))
