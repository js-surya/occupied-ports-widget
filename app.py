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


@app.get('/widget')
@app.get('/extension')
def widget():
    if not _authorized():
        return render_template_string('<div style="padding:0.5rem;color:var(--color-negative, var(--color-text-base, #e7edf7));">Unauthorized</div>'), 401

    if not _check_rate_limit():
        return render_template_string('<div style="padding:0.5rem;color:var(--color-negative, var(--color-text-base, #e7edf7));">Rate limit exceeded</div>'), 429

    payload = _get_payload()
    items = payload.get('items', []) if payload.get('ok') else []

    html = """
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <style>
        :root { color-scheme: light dark; }
        body { margin: 0; font-family: Inter, system-ui, sans-serif; }
        .ports-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 0.4rem;
        }
        .port-chip {
          text-align: center;
          padding: 0.28rem 0.2rem;
          border-radius: 6px;
          border: 1px solid color-mix(in srgb, var(--color-text-base, #cfd6e1) 16%, transparent);
          background: color-mix(in srgb, var(--color-widget-background, #11151b) 82%, var(--color-text-base, #cfd6e1) 18%);
          font-size: 1rem;
          font-weight: 600;
          color: var(--color-text-base, #e7edf7);
          opacity: 0.97;
        }
        .port-chip.reserved {
          border-color: color-mix(in srgb, var(--color-primary, #67b3ff) 42%, transparent);
          background: color-mix(in srgb, var(--color-widget-background, #11151b) 75%, var(--color-primary, #67b3ff) 25%);
          color: var(--color-primary, #67b3ff);
        }
        .status { margin-top: 0.55rem; font-size: 0.8rem; opacity: 0.8; }
        .toggle { margin-top: 0.45rem; font-size: 0.78rem; opacity: 0.86; }
        .bad { color: var(--color-negative, var(--color-text-base, #e7edf7)); }
        .ok { color: var(--color-positive, var(--color-primary, var(--color-text-base, #e7edf7))); }
      </style>
    </head>
    <body>
      {% if not payload.ok %}
        <div class="bad">Data unavailable</div>
        <div class="status">{{ payload.error }}</div>
      {% else %}
        <div class="ports-grid">
          {% for i in items[:16] %}
            <a class="port-chip {% if i.reserved %}reserved{% endif %}" href="{{ i.url }}" target="_blank" rel="noreferrer">{{ i.port }}</a>
          {% endfor %}
        </div>
        {% if items|length > 16 %}
          <div class="toggle">Showing first 16 of {{ items|length }} ports</div>
        {% endif %}
        <div class="status">{{ payload.count }} ports · sorted {{ payload.sort_mode }} · range {{ payload.min_port }}-{{ payload.max_port }}</div>
      {% endif %}

    </body>
    </html>
    """
    return render_template_string(html, payload=payload, items=items)


@app.get('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8789')))
