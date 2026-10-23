"""Read local initial credentials, verify real HTTP sessions, write only non-sensitive evidence."""
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://127.0.0.1:8080'


def exchange(opener, path, data=None, headers=None):
    request = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                     headers={'Content-Type': 'application/json', **(headers or {})})
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def run():
    credentials = json.loads((ROOT / 'runtime/private-config/accounts.json').read_text())
    results = []
    for username, role in [('member1', 'MEMBER'), ('member2', 'MEMBER'), ('reviewer', 'REVIEWER'), ('admin', 'ADMIN')]:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        status, token = exchange(opener, '/api/auth/csrf')
        assert status == 200
        csrf = token['data']
        before = next(cookie.value for cookie in jar if cookie.name == 'JSESSIONID')
        status, body = exchange(opener, '/api/auth/login', {'username': username, 'password': credentials[username]}, {csrf['headerName']: csrf['token']})
        assert status == 200 and body['data']['role'] == role
        assert next(cookie.value for cookie in jar if cookie.name == 'JSESSIONID') != before
        assert any(cookie.has_nonstandard_attr('HttpOnly') and cookie.get_nonstandard_attr('SameSite') == 'Lax' for cookie in jar)
        assert exchange(opener, '/api/auth/me')[0] == 200
        if role != 'ADMIN':
            assert exchange(opener, '/api/experiments')[0] == 403
        assert exchange(opener, '/api/auth/logout', {})[0] == 403
        _, token = exchange(opener, '/api/auth/csrf')
        csrf = token['data']
        assert exchange(opener, '/api/auth/logout', {}, {csrf['headerName']: csrf['token']})[0] == 200
        assert exchange(opener, '/api/auth/me')[0] == 401
        results.append({'account': username, 'role': role, 'login': 'PASS', 'sessionRotation': 'PASS', 'cookiePolicy': 'PASS', 'csrf': 'PASS', 'logout': 'PASS'})
    output = ROOT / 'docs/midterm/evidence/M02-http.json'
    output.write_text(json.dumps({'stage': 'M02', 'transport': 'actual HTTP on project Java:8080', 'results': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Real HTTP account/session probes: 4 PASS; no credentials recorded')


if __name__ == '__main__':
    run()
