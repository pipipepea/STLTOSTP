"""Generate a local API key without printing or committing it."""
from pathlib import Path
import secrets

path = Path(__file__).resolve().parents[1] / '.env'
text = path.read_text() if path.exists() else (path.parent / '.env.example').read_text()
lines = text.splitlines()
for i, line in enumerate(lines):
    if line.startswith('API_KEY='):
        if line.split('=', 1)[1] not in ('', 'replace-with-a-random-secret-at-least-24-characters'):
            print('Existing API_KEY preserved.')
            break
        lines[i] = 'API_KEY=' + secrets.token_urlsafe(32)
        path.write_text('\n'.join(lines)+'\n')
        path.chmod(0o600)
        print('Created .env with a random API_KEY. Read it locally to connect the UI.')
        break
else:
    raise SystemExit('Missing API_KEY entry in .env')
