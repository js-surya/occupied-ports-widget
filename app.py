import os
import time
import threading
from flask import Flask, jsonify, request, render_template_string
import requests

app = Flask(__name__)

DOCKER_API = os.getenv('DOCKER_API', 'http://occupied-ports-docker-proxy:2375/containers/json')
TIMEOUT = float(os.getenv('TIMEOUT_SECONDS', '6'))
CACHE_SECONDS = float(os.getenv('CACHE_SECONDS', '5'))
MIN_PORT = int(os.getenv('MIN_PORT', '1'))
MAX_PORT = int(os.getenv('MAX_PORT', '65535'))
SORT_MODE = os.getenv('SORT_MODE', 'asc').lower()  # asc | desc | recent
SHOW_SOURCE = os.getenv('SHOW_SOURCE', 'false').lower() == 'true'
LINK_SCHEME = os.getenv('LINK_SCHEME', 'http')
LINK_HOST = os.getenv('LINK_HOST', 'localhost')

AUTH_ENABLED = os.getenv('AUTH_ENABLED', 'false').lower() == 'true'
WIDGET_TOKEN = os.getenv('WIDGET_TOKEN', '')
DEBUG_ERRORS = os.getenv('DEBUG_ERRORS', 'false').lower() == 'true'
TRUST_PROXY = os.getenv('TRUST_PROXY', 'false').lower() == 'true'
RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '120'))

RESERVED_PORTS = {
    22: 'SSH',
    53: 'DNS',
    80: 'HTTP',
    123: 'NTP',
    443: 'HTTPS',
    3306: 'MySQL',
    5432: 'PostgreSQL',
}

_CACHE = {'ts': 0.0, 'payload': None}
_PORT_FIRST_SEEN = {}
_SEQ = 0

_RATE = {}
_RATE_LOCK = threading.Lock()


def _sort_items(items):
    if SORT_MODE == 'desc':
        return sorted(items, key=lambda x: x['port'], reverse=True)
    if SORT_MODE == 'recent':
        return sorted(items, key=lambda x: x.get('first_seen_order', 0), reverse=True)
    return sorted(items, key=lambda x: x['port'])


def _client_ip():
    if TRUST_PROXY:
        xff = request.headers.get('X-Forwarded-For', '')
        if xff:
            return xff.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _check_rate_limit():
    ip = _client_ip()
    now = int(time.time())
    window = now // 60

    with _RATE_LOCK:
        entry = _RATE.get(ip)
        if not entry or entry['window'] != window:
            _RATE[ip] = {'window': window, 'count': 1}
            return True

        entry['count'] += 1
        if entry['count'] > RATE_LIMIT_PER_MINUTE:
            return False

    return True


def _authorized():
    if not AUTH_ENABLED:
        return True

    if not WIDGET_TOKEN:
        return False

    token = request.headers.get('X-Widget-Token', '')
    return token == WIDGET_TOKEN


def _fetch_ports():
    global _SEQ
    res = requests.get(DOCKER_API, params={'all': 'false'}, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()

    seen = set()
    items = []

    for c in data:
        name = (c.get('Names') or ['unknown'])[0].lstrip('/')
        for p in (c.get('Ports') or []):
            public = p.get('PublicPort')
            proto = str(p.get('Type', 'tcp'))
            if not public:
                continue

            port = int(public)
            if port < MIN_PORT or port > MAX_PORT:
                continue

            if port in seen:
                continue
            seen.add(port)

            if port not in _PORT_FIRST_SEEN:
                _SEQ += 1
                _PORT_FIRST_SEEN[port] = _SEQ

            item = {
                'port': port,
                'proto': proto,
                'url': f'{LINK_SCHEME}://{LINK_HOST}:{port}',
                'reserved': port in RESERVED_PORTS,
                'reserved_label': RESERVED_PORTS.get(port, ''),
                'first_seen_order': _PORT_FIRST_SEEN[port],
            }
            if SHOW_SOURCE:
                item['source'] = name
            items.append(item)

    items = _sort_items(items)

    return {
        'ok': True,
        'error': '',
        'sort_mode': SORT_MODE,
        'min_port': MIN_PORT,
        'max_port': MAX_PORT,
        'count': len(items),
        'items': items,
    }


@app.after_request
def set_security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return resp


def _get_payload():
    now = time.time()
    if _CACHE['payload'] is not None and (now - _CACHE['ts']) < CACHE_SECONDS:
        return _CACHE['payload']

    try:
        payload = _fetch_ports()
        _CACHE['payload'] = payload
        _CACHE['ts'] = now
        return payload
    except Exception as e:
        payload = {
            'ok': False,
            'error': str(e) if DEBUG_ERRORS else 'temporarily unavailable',
            'sort_mode': SORT_MODE,
            'min_port': MIN_PORT,
            'max_port': MAX_PORT,
            'count': 0,
            'items': [],
        }
        _CACHE['payload'] = payload
        _CACHE['ts'] = now
        app.logger.exception('ports endpoint failed')
        return payload


@app.get('/ports')
def ports():
    if not _authorized():
        return jsonify({'ok': False, 'error': 'unauthorized', 'count': 0, 'items': []}), 401

    if not _check_rate_limit():
        return jsonify({'ok': False, 'error': 'rate limit exceeded', 'count': 0, 'items': []}), 429

    return jsonify(_get_payload())


@app.get('/check')
def check_port():
    if not _authorized():
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401

    if not _check_rate_limit():
        return jsonify({'ok': False, 'error': 'rate limit exceeded'}), 429

    port_raw = request.args.get('port', '').strip()
    if not port_raw.isdigit():
        return jsonify({'ok': False, 'error': 'invalid port'}), 400

    port = int(port_raw)
    if port < 1 or port > 65535:
        return jsonify({'ok': False, 'error': 'port out of range'}), 400

    payload = _get_payload()
    items = payload.get('items', []) if payload.get('ok') else []
    found = next((i for i in items if int(i.get('port', -1)) == port), None)

    return jsonify({
        'ok': True,
        'port': port,
        'occupied': found is not None,
        'reserved': bool(found.get('reserved')) if found else (port in RESERVED_PORTS),
        'reserved_label': (found.get('reserved_label') if found else RESERVED_PORTS.get(port, '')),
        'url': (found.get('url') if found else f'{LINK_SCHEME}://{LINK_HOST}:{port}'),
    })


@app.get('/check-ui')
def check_port_ui():
    port_raw = request.args.get('port', '').strip()
    result = None
    error = ''

    if port_raw:
        if not port_raw.isdigit():
            error = 'Enter a valid numeric port (1-65535).'
        else:
            port = int(port_raw)
            if port < 1 or port > 65535:
                error = 'Port must be between 1 and 65535.'
            else:
                payload = _get_payload()
                items = payload.get('items', []) if payload.get('ok') else []
                found = next((i for i in items if int(i.get('port', -1)) == port), None)
                result = {
                    'port': port,
                    'occupied': found is not None,
                    'url': (found.get('url') if found else f'{LINK_SCHEME}://{LINK_HOST}:{port}'),
                }

    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Port Check</title>
      <style>
        body { font-family: Inter, system-ui, sans-serif; max-width: 540px; margin: 2rem auto; padding: 0 1rem; background: #0b0d10; color: #e8edf4; }
        .card { border: 1px solid #2a2f36; border-radius: 10px; padding: 1rem; background: #12161b; }
        input, button { font-size: 1rem; padding: 0.55rem 0.7rem; border-radius: 8px; border: 1px solid #2f3640; background: #0e1217; color: #e8edf4; }
        button { cursor: pointer; margin-left: 0.4rem; }
        .ok { color: #66d17a; }
        .bad { color: #ff6b6b; }
        a { color: #82b4ff; }
      </style>
    </head>
    <body>
      <div class="card">
        <h3 style="margin-top:0;">Check Port Availability</h3>
        <form method="get" action="/check-ui">
          <input type="number" name="port" min="1" max="65535" placeholder="Enter port" value="{{ port_raw }}" required>
          <button type="submit">Check</button>
        </form>

        {% if error %}
          <p class="bad">{{ error }}</p>
        {% endif %}

        {% if result %}
          {% if result.occupied %}
            <p class="bad"><strong>Port {{ result.port }} is occupied.</strong></p>
            <p><a href="{{ result.url }}" target="_blank" rel="noreferrer">Open {{ result.url }}</a></p>
          {% else %}
            <p class="ok"><strong>Port {{ result.port }} is free.</strong></p>
          {% endif %}
        {% endif %}
      </div>
    </body>
    </html>
    """
    return render_template_string(html, port_raw=port_raw, result=result, error=error)


@app.get('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8789')))
