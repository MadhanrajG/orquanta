import ast, re, time
from pathlib import Path

SKIP = {'node_modules','__pycache__','.git','.venv','dist'}
root = Path(r'c:\ai-gpu-cloud\v4')

ok = 0
fail = []
for f in root.rglob('*.py'):
    if any(s in f.parts for s in SKIP):
        continue
    try:
        ast.parse(f.read_text(encoding='utf-8', errors='ignore'))
        ok += 1
    except SyntaxError as e:
        fail.append(f'{f.relative_to(root)}: line {e.lineno} - {e.msg}')

print(f'SYNTAX CHECK: {ok} files OK, {len(fail)} FAIL')
for item in fail[:10]:
    print(f'  FAIL: {item}')

# Security scan - hardcoded secrets
print()
DANGER = re.compile(r'(?i)(password\s*=\s*["\'][^"\']{8,}["\']|api_key\s*=\s*["\'][^"\']{8,}["\']|secret\s*=\s*["\'][^"\']{8,}["\'])')
SAFE_VALS = {'your_', 'change_', 'replace', 'example', 'placeholder', 'xxxx', 'test', 'demo', 'orquanta-', 'dummy'}
secret_hits = []
for f in root.rglob('*.py'):
    if any(s in f.parts for s in SKIP):
        continue
    try:
        txt = f.read_text(encoding='utf-8', errors='ignore')
        for m in DANGER.finditer(txt):
            val = m.group(0).lower()
            if not any(safe in val for safe in SAFE_VALS):
                secret_hits.append(f'{f.relative_to(root)}: {m.group(0)[:60]}')
    except:
        pass

if secret_hits:
    print(f'SECURITY: {len(secret_hits)} potential hardcoded secrets')
    for h in secret_hits[:5]:
        print(f'  WARN: {h}')
else:
    print('SECURITY: PASS - No hardcoded secrets found')

# Import check for key modules
print()
modules_to_check = [
    ('v4.api.main', 'FastAPI app'),
    ('v4.agents.master_orchestrator', 'OrMind'),
    ('v4.providers.provider_router', 'Provider Router'),
    ('v4.billing.stripe_integration', 'Stripe'),
    ('v4.intelligence.carbon_tracker', 'Carbon Tracker'),
    ('v4.sdk.orquanta_sdk', 'Python SDK'),
    ('v4.sdk.orquanta_cli', 'CLI'),
    ('v4.monitoring.metrics_exporter', 'Metrics'),
]
import sys
sys.path.insert(0, r'c:\ai-gpu-cloud')
for module, name in modules_to_check:
    try:
        __import__(module)
        print(f'IMPORT OK: {name} ({module})')
    except ModuleNotFoundError as e:
        missing = str(e).split("'")[1] if "'" in str(e) else str(e)
        if missing in ('asyncpg','psycopg2','stripe','prometheus_client','celery','redis','chromadb','jose','passlib'):
            print(f'IMPORT WARN (runtime dep): {name} - missing {missing}')
        else:
            print(f'IMPORT FAIL: {name} - {e}')
    except Exception as e:
        print(f'IMPORT FAIL: {name} - {type(e).__name__}: {str(e)[:80]}')

print()
print('SYNTAX+SECURITY+IMPORT SCAN COMPLETE')
