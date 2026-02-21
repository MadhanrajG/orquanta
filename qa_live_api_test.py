"""
OrQuanta Platform Startup — API Health + Load Test
Run this AFTER quickstart.py is running on localhost:8000
"""
import urllib.request, urllib.error, json, time, threading, sys

BASE = 'http://localhost:8000'
TIMEOUT = 5

def test_endpoint(method, path, data=None, headers=None, token=None):
    url = BASE + path
    hdrs = {'Content-Type': 'application/json'}
    if token:
        hdrs['Authorization'] = f'Bearer {token}'
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        t0 = time.time()
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        ms = (time.time()-t0)*1000
        body = json.loads(resp.read())
        return True, resp.status, ms, body
    except urllib.error.HTTPError as e:
        ms = 0
        try: body = json.loads(e.read())
        except: body = {}
        return False, e.code, ms, body
    except Exception as e:
        return False, 0, 0, str(e)

print("="*60)
print("PHASE 1: API HEALTH CHECKS")
print("="*60)

endpoints = [
    ('GET',  '/health'),
    ('GET',  '/providers/prices?gpu_type=A100'),
    ('GET',  '/providers/health'),
    ('GET',  '/demo'),
    ('GET',  '/agents/status'),
    ('GET',  '/metrics/platform'),
]

api_results = []
for method, path in endpoints:
    ok, status, ms, body = test_endpoint(method, path)
    icon = '✅' if ok else '❌'
    print(f'{icon} {method} {path} → {status} ({ms:.0f}ms)')
    api_results.append((path, ok, ms))

print()
print("="*60)
print("PHASE 1: AUTHENTICATION TESTS")
print("="*60)

# Register
ok, status, ms, body = test_endpoint('POST', '/auth/register',
    data=json.dumps({'email':'priya@mlstartup.in','password':'TestUser123!',
                     'name':'Priya Sharma','organization':'ML Startup India'}).encode())
print(f'{"✅" if ok else "❌"} Register → {status} ({ms:.0f}ms)')
if not ok and status == 400:
    print(f'  (User may already exist - trying login)')

# Login
ok, status, ms, body = test_endpoint('POST', '/auth/login',
    data=json.dumps({'email':'priya@mlstartup.in','password':'TestUser123!'}).encode())
token = body.get('access_token') if ok else None
print(f'{"✅" if token else "❌"} Login → {status} ({ms:.0f}ms)')

# Protected endpoint with token
if token:
    ok, status, ms, body = test_endpoint('GET', '/jobs', token=token)
    print(f'{"✅" if ok else "❌"} Protected /jobs with token → {status} ({ms:.0f}ms)')

    # Invalid token
    ok2, status2, ms2, body2 = test_endpoint('GET', '/jobs', token='invalid.token.here')
    print(f'{"✅" if not ok2 and status2==401 else "❌"} Invalid token rejected → {status2}')

print()
print("="*60)
print("PHASE 1: GOAL SUBMISSION (Priya's use case)")
print("="*60)

if token:
    ok, status, ms, body = test_endpoint('POST', '/goals',
        data=json.dumps({'description':'Fine-tune Llama 3 8B on 10GB customer support data, budget under 80 dollars',
                         'budget_usd':80.0,'priority':'normal'}).encode(),
        token=token)
    print(f'{"✅" if ok else "❌"} Goal submission → {status} ({ms:.0f}ms)')
    if ok:
        print(f'  Goal ID: {body.get("goal_id","?")}')
        print(f'  Status: {body.get("status","?")}')
        print(f'  Estimated cost: {body.get("estimated_cost","?")}')
else:
    print('⚠️  Skipped - no auth token')

print()
print("="*60)
print("PHASE 2: SECURITY TESTS")
print("="*60)

if token:
    # SQL injection
    ok, s, ms, b = test_endpoint('POST', '/goals',
        data=json.dumps({'description':"'; DROP TABLE jobs; --",'budget_usd':10}).encode(), token=token)
    print(f'{"✅" if s != 500 else "❌"} SQL injection → {s} ({"blocked/handled" if s in (200,201,400,422) else "might be vulnerable"})')

    # Budget overflow / negative
    ok, s, ms, b = test_endpoint('POST', '/goals',
        data=json.dumps({'description':'test','budget_usd':-999999}).encode(), token=token)
    print(f'{"✅" if s in (400,422) else "❌"} Negative budget → {s} ({"rejected" if s in (400,422) else "accepted - FIX NEEDED"})')

    # No auth - admin endpoint
    ok, s, ms, b = test_endpoint('GET', '/admin/users')
    print(f'{"✅" if s in (401,403,404) else "❌"} /admin without token → {s}')
else:
    print('⚠️  Security tests skipped - no auth token')

print()
print("="*60)
print("PHASE 2: LOAD TEST — 50 concurrent users")
print("="*60)

results = {'ok': 0, 'fail': 0, 'times': []}
lock = threading.Lock()

def hit():
    t0 = time.time()
    try:
        urllib.request.urlopen(f'{BASE}/health', timeout=10)
        with lock:
            results['ok'] += 1
            results['times'].append((time.time()-t0)*1000)
    except:
        with lock:
            results['fail'] += 1

threads = [threading.Thread(target=hit) for _ in range(50)]
t_start = time.time()
for t in threads: t.start()
for t in threads: t.join()
total = time.time()-t_start
avg_ms = sum(results['times'])/len(results['times']) if results['times'] else 9999
icon = '✅' if results['ok'] >= 48 else '⚠️' if results['ok'] >= 40 else '❌'
print(f'{icon} 50 concurrent requests in {total:.2f}s')
print(f'   Success: {results["ok"]}/50 | Failed: {results["fail"]}/50')
print(f'   Avg response: {avg_ms:.0f}ms')

print()
print("LIVE API TESTS COMPLETE")
print(f'Time: {time.strftime("%Y-%m-%d %H:%M:%S")}')
