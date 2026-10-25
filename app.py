import ipaddress
import os
import threading
import time

import requests
from flask import Flask, jsonify, render_template_string, request

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
FRAME_ANCESTORS = os.getenv('FRAME_ANCESTORS', "'self'")

AUTH_ENABLED = os.getenv('AUTH_ENABLED', 'false').lower() == 'true'
WIDGET_TOKEN = os.getenv('WIDGET_TOKEN', '')
DEBUG_ERRORS = os.getenv('DEBUG_ERRORS', 'false').lower() == 'true'
TRUST_PROXY = os.getenv('TRUST_PROXY', 'false').lower() == 'true'
RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', '120'))

TAILSCALE_IPV4 = ipaddress.ip_network('100.64.0.0/10')
TAILSCALE_IPV6 = ipaddress.ip_network('fd7a:115c:a1e0::/48')
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
_CACHE_LOCK = threading.Lock()
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
        for client, state in list(_RATE.items()):
            if state['window'] != window:
                del _RATE[client]
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


def _normalize_host_ip(value):
    value = (value or '').strip()
    if not value:
        return '0.0.0.0'
    if value == '::0':
        return '::'
    return value


def _scope_for_ip(value):
    host_ip = _normalize_host_ip(value)
    if host_ip in {'0.0.0.0', '::'}:
        return 'public'
    if host_ip.startswith('127.') or host_ip == '::1':
        return 'loopback'

    try:
        parsed = ipaddress.ip_address(host_ip)
    except ValueError:
        return 'unknown'

    if parsed.version == 4 and parsed in TAILSCALE_IPV4:
        return 'tailscale'
    if parsed.version == 6 and parsed in TAILSCALE_IPV6:
        return 'tailscale'
    if parsed.is_private:
        return 'private'
    return 'public'


def _scope_rank(scope):
    order = {
        'public': 0,
        'mixed': 1,
        'tailscale': 2,
        'private': 3,
        'loopback': 4,
        'unknown': 5,
    }
    return order.get(scope, 99)


def _finalize_item(item):
    protocols = sorted(item.pop('_protocols'))
    host_ips = sorted(item.pop('_host_ips'))
    exposure_scopes = sorted(item.pop('_exposure_scopes'), key=_scope_rank)
    private_ports = sorted(item.pop('_private_ports'))
    sources = sorted(item.pop('_sources'))

    exposure_scope = exposure_scopes[0] if len(exposure_scopes) == 1 else 'mixed'
    item['proto'] = protocols[0]
    item['protocols'] = protocols
    item['host_ips'] = host_ips
    item['exposure_scope'] = exposure_scope
    item['exposure_scopes'] = exposure_scopes
    item['private_ports'] = private_ports
    item['primary_host_ip'] = host_ips[0] if host_ips else ''

    if SHOW_SOURCE:
        item['source'] = sources[0] if len(sources) == 1 else ', '.join(sources)
        item['sources'] = sources
        item['source_count'] = len(sources)

    return item


def _fetch_ports():
    global _SEQ
    res = requests.get(DOCKER_API, params={'all': 'false'}, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()

    items_by_port = {}

    for c in data:
        name = (c.get('Names') or ['unknown'])[0].lstrip('/')
        for p in (c.get('Ports') or []):
            public = p.get('PublicPort')
            if not public:
                continue

            port = int(public)
            if port < MIN_PORT or port > MAX_PORT:
                continue

            if port not in _PORT_FIRST_SEEN:
                _SEQ += 1
                _PORT_FIRST_SEEN[port] = _SEQ

            item = items_by_port.setdefault(
                port,
                {
                    'port': port,
                    'url': f'{LINK_SCHEME}://{LINK_HOST}:{port}',
                    'reserved': port in RESERVED_PORTS,
                    'reserved_label': RESERVED_PORTS.get(port, ''),
                    'first_seen_order': _PORT_FIRST_SEEN[port],
                    '_protocols': set(),
                    '_host_ips': set(),
                    '_exposure_scopes': set(),
                    '_private_ports': set(),
                    '_sources': set(),
                },
            )

            proto = str(p.get('Type', 'tcp'))
            host_ip = _normalize_host_ip(p.get('IP'))
            private_port = p.get('PrivatePort')

            item['_protocols'].add(proto)
            item['_host_ips'].add(host_ip)
            item['_exposure_scopes'].add(_scope_for_ip(host_ip))
            if private_port is not None:
                item['_private_ports'].add(int(private_port))
            if SHOW_SOURCE:
                item['_sources'].add(name)

    items = [_finalize_item(item) for item in items_by_port.values()]
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
    if request.endpoint == 'widget':
        resp.headers['Content-Security-Policy'] = f'frame-ancestors {FRAME_ANCESTORS}'
    else:
        resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return resp


def _get_payload():
    # Serialize refreshes so threaded requests share a consistent cache and order.
    with _CACHE_LOCK:
        return _get_payload_locked()


def _get_payload_locked():
    now = time.monotonic()
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
          text-decoration: none;
        }
        .port-chip.reserved {
          border-color: color-mix(in srgb, var(--color-primary, #67b3ff) 42%, transparent);
          background: color-mix(in srgb, var(--color-widget-background, #11151b) 75%, var(--color-primary, #67b3ff) 25%);
          color: var(--color-primary, #67b3ff);
        }
        .port-chip.public {
          border-color: color-mix(in srgb, #ff7b72 46%, transparent);
          background: color-mix(in srgb, var(--color-widget-background, #11151b) 70%, #ff7b72 30%);
        }
        .port-chip.tailscale {
          border-color: color-mix(in srgb, #6eb6ff 46%, transparent);
        }
        .port-chip.private {
          border-color: color-mix(in srgb, #f2cc60 42%, transparent);
        }
        .port-chip.loopback {
          border-color: color-mix(in srgb, #3fb950 42%, transparent);
        }
        .port-chip.mixed {
          border-style: dashed;
        }
        .ports-collapse { margin-top: 0.1rem; }
        .ports-collapse summary {
          cursor: pointer;
          list-style: none;
        }
        .ports-collapse summary::-webkit-details-marker { display: none; }
        .status { margin-top: 0.55rem; font-size: 0.8rem; opacity: 0.8; }
        .toggle { margin-top: 0.45rem; margin-bottom: 0.55rem; font-size: 0.78rem; opacity: 0.86; }
        .legend {
          margin-top: 0.45rem;
          font-size: 0.74rem;
          opacity: 0.82;
          display: flex;
          flex-wrap: wrap;
          gap: 0.5rem;
        }
        .legend span::before {
          content: '•';
          margin-right: 0.2rem;
        }
        .legend .public::before { color: #ff7b72; }
        .legend .tailscale::before { color: #6eb6ff; }
        .legend .private::before { color: #f2cc60; }
        .legend .loopback::before { color: #3fb950; }
        .legend .mixed::before { color: #c9d1d9; }
        .bad { color: var(--color-negative, var(--color-text-base, #e7edf7)); }
      </style>
    </head>
    <body>
      <div id="widget-root">
      {% if not payload.ok %}
        <div class="bad">Data unavailable</div>
        <div class="status">{{ payload.error }}</div>
      {% else %}
        <details class="ports-collapse" {% if items|length <= 16 %}open{% endif %}>
          <summary class="toggle">{{ payload.count }} ports · sorted {{ payload.sort_mode }} · range {{ payload.min_port }}-{{ payload.max_port }}</summary>
          <div class="ports-grid">
            {% for i in items %}
              <a class="port-chip {{ i.exposure_scope }} {% if i.reserved %}reserved{% endif %}" href="{{ i.url }}" title="{{ i.port }} · {{ i.exposure_scope }} · {{ i.protocols | join(', ') }} · {{ i.host_ips | join(', ') }}{% if i.sources %} · {{ i.sources | join(', ') }}{% endif %}" target="_blank" rel="noreferrer">{{ i.port }}</a>
            {% endfor %}
          </div>
          <div class="legend">
            <span class="public">public</span>
            <span class="tailscale">tailscale</span>
            <span class="private">private</span>
            <span class="loopback">loopback</span>
            <span class="mixed">mixed</span>
          </div>
        </details>
      {% endif %}
      </div>
      <script>
        const POLL_MS = 3000;
        const root = document.getElementById('widget-root');
        const escapeHtml = (s) => String(s)
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');

        function renderPayload(payload) {
          if (!payload.ok) {
            root.innerHTML = `<div class="bad">Data unavailable</div><div class="status">${escapeHtml(payload.error || 'temporarily unavailable')}</div>`;
            return;
          }

          const items = Array.isArray(payload.items) ? payload.items : [];
          const chips = items.map((i) => {
            const reserved = i.reserved ? ' reserved' : '';
            const scope = escapeHtml(i.exposure_scope || 'unknown');
            const protocols = Array.isArray(i.protocols) ? i.protocols.join(', ') : '';
            const hostIps = Array.isArray(i.host_ips) ? i.host_ips.join(', ') : '';
            const sources = Array.isArray(i.sources) && i.sources.length ? ` · ${i.sources.join(', ')}` : '';
            const title = `${i.port} · ${i.exposure_scope || 'unknown'} · ${protocols} · ${hostIps}${sources}`;
            return `<a class="port-chip ${scope}${reserved}" href="${escapeHtml(i.url)}" title="${escapeHtml(title)}" target="_blank" rel="noreferrer">${escapeHtml(i.port)}</a>`;
          }).join('');

          const previous = root.querySelector('details');
          const isOpen = previous ? previous.open : items.length <= 16;
          const openAttr = isOpen ? ' open' : '';
          root.innerHTML = `
            <details class="ports-collapse"${openAttr}>
              <summary class="toggle">${escapeHtml(payload.count)} ports · sorted ${escapeHtml(payload.sort_mode)} · range ${escapeHtml(payload.min_port)}-${escapeHtml(payload.max_port)}</summary>
              <div class="ports-grid">${chips}</div>
              <div class="legend">
                <span class="public">public</span>
                <span class="tailscale">tailscale</span>
                <span class="private">private</span>
                <span class="loopback">loopback</span>
                <span class="mixed">mixed</span>
              </div>
            </details>
          `;
        }

        async function refreshPorts() {
          try {
            const res = await fetch(new URL('ports', window.location.href), { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const payload = await res.json();
            renderPayload(payload);
          } catch (_) {
            // keep last good render
          }
        }

        setInterval(refreshPorts, POLL_MS);
      </script>
    </body>
    </html>
    """
    return render_template_string(html, payload=payload, items=items)


@app.get('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8789')))
