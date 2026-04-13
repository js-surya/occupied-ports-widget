import os
from flask import Flask, jsonify
import requests

app = Flask(__name__)
DOCKER_API = os.getenv('DOCKER_API', 'http://occupied-ports-docker-proxy:2375/containers/json')
TIMEOUT = float(os.getenv('TIMEOUT_SECONDS', '6'))


@app.get('/ports')
def ports():
    try:
        res = requests.get(DOCKER_API, params={'all': 'false'}, timeout=TIMEOUT)
        res.raise_for_status()
        data = res.json()

        seen = set()
        items = []

        for c in data:
            for p in (c.get('Ports') or []):
                public = p.get('PublicPort')
                proto = p.get('Type', 'tcp')
                if not public:
                    continue
                port = int(public)
                if port in seen:
                    continue
                seen.add(port)
                items.append({'port': port, 'proto': str(proto)})

        items.sort(key=lambda x: x['port'])
        return jsonify({'items': items})
    except Exception:
        return jsonify({'items': []})


@app.get('/health')
def health():
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8789')))
