import os
import time
from flask import Flask, jsonify
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


def _sort_items(items):
    if SORT_MODE == 'desc':
        return sorted(items, key=lambda x: x['port'], reverse=True)
    if SORT_MODE == 'recent':
        return sorted(items, key=lambda x: x.get('first_seen_order', 0), reverse=True)
    return sorted(items, key=lambda x: x['port'])


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

    payload = {
        'ok': True,
        'error': '',
        'sort_mode': SORT_MODE,
        'min_port': MIN_PORT,
        'max_port': MAX_PORT,
        'count': len(items),
        'items': items,
    }
    return payload


@app.get('/ports')
def ports():
    now = time.time()
    if _CACHE['payload'] is not None and (now - _CACHE['ts']) < CACHE_SECONDS:
        return jsonify(_CACHE['payload'])

    try:
        payload = _fetch_ports()
        _CACHE['payload'] = payload
        _CACHE['ts'] = now
        return jsonify(payload)
    except Exception as e:
        payload = {
            'ok': False,
            'error': str(e),
            'sort_mode': SORT_MODE,
            'min_port': MIN_PORT,
            'max_port': MAX_PORT,
            'count': 0,
            'items': [],
        }
        _CACHE['payload'] = payload
        _CACHE['ts'] = now
        return jsonify(payload)


@app.get('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8789')))
