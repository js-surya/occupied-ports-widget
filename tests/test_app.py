from unittest.mock import patch

import app as app_module
from app import app


def _reset_cache():
    app_module._CACHE['payload'] = None
    app_module._CACHE['ts'] = 0
    app_module._PORT_FIRST_SEEN.clear()
    app_module._RATE.clear()
    app_module._SEQ = 0


def test_health():
    client = app.test_client()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {'ok': True}


def test_ports_include_scope_protocols_and_sources():
    fake_data = [
        {
            'Names': ['/glance'],
            'Ports': [
                {'IP': '127.0.0.1', 'PublicPort': 8088, 'PrivatePort': 8080, 'Type': 'tcp'},
                {'IP': '100.78.209.116', 'PublicPort': 53, 'PrivatePort': 53, 'Type': 'udp'},
            ],
        },
        {
            'Names': ['/pihole'],
            'Ports': [
                {'IP': '127.0.0.1', 'PublicPort': 53, 'PrivatePort': 53, 'Type': 'tcp'},
                {'IP': '100.78.209.116', 'PublicPort': 53, 'PrivatePort': 53, 'Type': 'tcp'},
            ],
        },
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0), patch.object(app_module, 'SHOW_SOURCE', True):
            _reset_cache()
            client = app.test_client()
            response = client.get('/ports')

    assert response.status_code == 200
    payload = response.json
    assert payload['ok'] is True
    assert payload['count'] == 2

    dns_item = payload['items'][0]
    assert dns_item['port'] == 53
    assert dns_item['reserved'] is True
    assert dns_item['reserved_label'] == 'DNS'
    assert dns_item['protocols'] == ['tcp', 'udp']
    assert dns_item['host_ips'] == ['100.78.209.116', '127.0.0.1']
    assert dns_item['exposure_scope'] == 'mixed'
    assert dns_item['exposure_scopes'] == ['tailscale', 'loopback']
    assert dns_item['private_ports'] == [53]
    assert dns_item['sources'] == ['glance', 'pihole']
    assert dns_item['source_count'] == 2
    assert dns_item['source'] == 'glance, pihole'

    glance_item = payload['items'][1]
    assert glance_item['port'] == 8088
    assert glance_item['exposure_scope'] == 'loopback'
    assert glance_item['host_ips'] == ['127.0.0.1']
    assert glance_item['private_ports'] == [8080]


def test_ports_filter_and_desc_sort():
    fake_data = [
        {
            'Names': ['/sample'],
            'Ports': [
                {'IP': '0.0.0.0', 'PublicPort': 22, 'PrivatePort': 22, 'Type': 'tcp'},
                {'IP': '0.0.0.0', 'PublicPort': 8088, 'PrivatePort': 8080, 'Type': 'tcp'},
                {'IP': '0.0.0.0', 'PublicPort': 3001, 'PrivatePort': 3001, 'Type': 'tcp'},
            ]
        }
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0), patch.object(app_module, 'MIN_PORT', 1000), patch.object(app_module, 'MAX_PORT', 9000), patch.object(app_module, 'SORT_MODE', 'desc'):
            _reset_cache()
            client = app.test_client()
            response = client.get('/ports')

    assert response.status_code == 200
    assert response.json['ok'] is True
    ports = [item['port'] for item in response.json['items']]
    assert ports == [8088, 3001]


def test_auth_enabled_blocks_without_token():
    with patch.object(app_module, 'AUTH_ENABLED', True), patch.object(app_module, 'WIDGET_TOKEN', 'abc123'):
        _reset_cache()
        client = app.test_client()
        response = client.get('/ports')
    assert response.status_code == 401
    assert response.json['ok'] is False


def test_auth_enabled_accepts_with_token():
    fake_data = [{'Names': ['/widget'], 'Ports': [{'IP': '127.0.0.1', 'PublicPort': 8088, 'PrivatePort': 8080, 'Type': 'tcp'}]}]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'AUTH_ENABLED', True), patch.object(app_module, 'WIDGET_TOKEN', 'abc123'), patch.object(app_module, 'CACHE_SECONDS', 0):
            _reset_cache()
            client = app.test_client()
            response = client.get('/ports', headers={'X-Widget-Token': 'abc123'})

    assert response.status_code == 200
    assert response.json['ok'] is True


def test_rate_limit():
    fake_data = [{'Names': ['/widget'], 'Ports': [{'IP': '127.0.0.1', 'PublicPort': 8088, 'PrivatePort': 8080, 'Type': 'tcp'}]}]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0), patch.object(app_module, 'RATE_LIMIT_PER_MINUTE', 1):
            _reset_cache()
            client = app.test_client()
            r1 = client.get('/ports')
            r2 = client.get('/ports')

    assert r1.status_code == 200
    assert r2.status_code == 429


def test_widget_renders_scope_classes_and_tooltips():
    fake_data = [
        {
            'Names': ['/public-service'],
            'Ports': [{'IP': '0.0.0.0', 'PublicPort': 443, 'PrivatePort': 8443, 'Type': 'tcp'}],
        }
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0), patch.object(app_module, 'SHOW_SOURCE', True):
            _reset_cache()
            client = app.test_client()
            response = client.get('/widget')

    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'port-chip public reserved' in text
    assert 'title="443 · public · tcp · 0.0.0.0 · public-service"' in text
    assert 'public' in text
    assert 'loopback' in text


def test_widget_unauthorized():
    with patch.object(app_module, 'AUTH_ENABLED', True), patch.object(app_module, 'WIDGET_TOKEN', 'abc123'):
        _reset_cache()
        client = app.test_client()
        response = client.get('/widget')

    assert response.status_code == 401
    assert 'Unauthorized' in response.get_data(as_text=True)


def test_widget_rate_limit():
    fake_data = [{'Names': ['/widget'], 'Ports': [{'IP': '127.0.0.1', 'PublicPort': 8088, 'PrivatePort': 8080, 'Type': 'tcp'}]}]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0), patch.object(app_module, 'RATE_LIMIT_PER_MINUTE', 1):
            _reset_cache()
            client = app.test_client()
            response_one = client.get('/widget')
            response_two = client.get('/widget')

    assert response_one.status_code == 200
    assert response_two.status_code == 429
    assert 'Rate limit exceeded' in response_two.get_data(as_text=True)
