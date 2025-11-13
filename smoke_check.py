import requests, time

base = 'http://127.0.0.1:5000'
for i in range(20):
    try:
        r = requests.get(base + '/api/health', timeout=1)
        if r.ok:
            break
    except Exception:
        time.sleep(0.5)

print('health', r.status_code if 'r' in locals() else 'no response')

user = {'email': 'ci+tester@example.com', 'password': 'Testpass123', 'name': 'CI Tester'}
try:
    r = requests.post(base + '/api/auth/register', json=user)
    print('register', r.status_code, r.text)
except Exception as e:
    print('register error', e)

try:
    r = requests.post(base + '/api/auth/login', json={'email': user['email'], 'password': user['password']})
    print('login', r.status_code, r.text)
    token = r.json().get('access_token') if r.ok else None
except Exception as e:
    print('login error', e)
    token = None

if token:
    h = {'Authorization': 'Bearer ' + token}
    p = requests.get(base + '/api/projects', headers=h)
    b = requests.get(base + '/api/bugs', headers=h)
    a = requests.get(base + '/api/bugs/analytics', headers=h)
    print('projects', p.status_code, p.text[:500])
    print('bugs', b.status_code, b.text[:500])
    print('analytics', a.status_code, a.text[:500])
else:
    print('no token obtained')
