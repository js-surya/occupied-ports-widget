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


@app.get('/check-fragment')
def check_fragment():
    if not _authorized():
        return render_template_string('<div style="color:#ff6b6b;font-size:0.82rem;">Unauthorized</div>'), 401

    if not _check_rate_limit():
        return render_template_string('<div style="color:#ff6b6b;font-size:0.82rem;">Rate limit exceeded</div>'), 429

    port_raw = request.args.get('port', '').strip()
    if not port_raw.isdigit():
        return render_template_string('<div style="color:#ff6b6b;font-size:0.82rem;">Enter a valid port (1-65535).</div>')

    port = int(port_raw)
    if port < 1 or port > 65535:
        return render_template_string('<div style="color:#ff6b6b;font-size:0.82rem;">Enter a valid port (1-65535).</div>')

    payload = _get_payload()
    items = payload.get('items', []) if payload.get('ok') else []
    occupied = any(int(i.get('port', -1)) == port for i in items)

    if occupied:
        return render_template_string('<div style="color:#ff6b6b;font-size:0.82rem;">Port {{p}} is occupied</div>', p=port)
    return render_template_string('<div style="color:#66d17a;font-size:0.82rem;">Port {{p}} is free</div>', p=port)


@app.get('/widget')
def widget():
    if not _authorized():
        return render_template_string('<div style="padding:0.5rem;color:#ff6b6b;">Unauthorized</div>'), 401

    if not _check_rate_limit():
        return render_template_string('<div style="padding:0.5rem;color:#ff6b6b;">Rate limit exceeded</div>'), 429

    payload = _get_payload()
    items = payload.get('items', []) if payload.get('ok') else []

    port_raw = request.args.get('port', '').strip()
    result = None
    if port_raw:
        if port_raw.isdigit() and 1 <= int(port_raw) <= 65535:
            p = int(port_raw)
            found = next((i for i in items if int(i.get('port', -1)) == p), None)
            result = {'port': p, 'occupied': found is not None}
        else:
            result = {'error': 'Enter a valid port (1-65535).'}

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
        .row { margin-top: 0.55rem; display: flex; gap: 0.4rem; align-items: center; }
        .row input {
          width: 100%; padding: 0.35rem 0.5rem; border-radius: 6px;
          border: 1px solid color-mix(in srgb, var(--color-text-base, #cfd6e1) 18%, transparent);
          background: color-mix(in srgb, var(--color-widget-background, #11151b) 88%, var(--color-text-base, #cfd6e1) 12%);
          color: var(--color-text-base, #e7edf7);
        }
        .row button {
          padding: 0.35rem 0.6rem; border-radius: 6px;
          border: 1px solid color-mix(in srgb, var(--color-text-base, #cfd6e1) 20%, transparent);
          background: color-mix(in srgb, var(--color-widget-background, #11151b) 75%, var(--color-primary, #67b3ff) 25%);
          color: var(--color-text-base, #e7edf7); cursor: pointer;
        }
        .toggle { margin-top: 0.45rem; font-size: 0.78rem; opacity: 0.86; }
        .bad { color: #ff6b6b; }
        .ok { color: #66d17a; }
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

      <form class="row" method="get" action="/check-fragment" target="port-check-result-frame">
        <input name="port" type="number" min="1" max="65535" placeholder="Check port" value="{{ port_raw }}" required />
        <button type="submit">Check</button>
      </form>

      <iframe
        name="port-check-result-frame"
        title="Port check result"
        style="margin-top:0.35rem;width:100%;height:1.6rem;border:0;background:transparent;"
      ></iframe>
    </body>
    </html>
    """
    return render_template_string(html, payload=payload, items=items, result=result, port_raw=port_raw)


@app.get('/check-ui')
def check_port_ui():
    # Legacy endpoint kept for backward compatibility.
    return widget()


@app.get('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8789')))
