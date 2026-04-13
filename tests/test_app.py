from unittest.mock import patch

import app as app_module
from app import app


def _reset_cache():
    app_module._CACHE['payload'] = None
    app_module._CACHE['ts'] = 0


def test_health():
    client = app.test_client()
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {'ok': True}


def test_ports_dedup_and_sort():
    fake_data = [
        {
            'Ports': [
                {'PublicPort': 8088, 'Type': 'tcp'},
                {'PublicPort': 53, 'Type': 'udp'},
            ]
        },
        {
            'Ports': [
                {'PublicPort': 53, 'Type': 'tcp'},
                {'PublicPort': 3001, 'Type': 'tcp'},
            ]
        },
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0):
            _reset_cache()
            client = app.test_client()
            response = client.get('/ports')

    assert response.status_code == 200
    assert response.json['ok'] is True
    assert response.json['count'] == 3
    assert response.json['items'][0]['port'] == 53
    assert response.json['items'][1]['port'] == 3001
    assert response.json['items'][2]['port'] == 8088
    assert response.json['items'][0]['reserved'] is True


def test_ports_filter_and_desc_sort():
    fake_data = [
        {
            'Ports': [
                {'PublicPort': 22, 'Type': 'tcp'},
                {'PublicPort': 8088, 'Type': 'tcp'},
                {'PublicPort': 3001, 'Type': 'tcp'},
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
    fake_data = [{'Ports': [{'PublicPort': 8088, 'Type': 'tcp'}]}]

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
    fake_data = [{'Ports': [{'PublicPort': 8088, 'Type': 'tcp'}]}]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return fake_data

    with patch('app.requests.get', return_value=FakeResponse()):
        with patch.object(app_module, 'CACHE_SECONDS', 0), patch.object(app_module, 'RATE_LIMIT_PER_MINUTE', 1):
            _reset_cache()
            app_module._RATE.clear()
            client = app.test_client()
            r1 = client.get('/ports')
            r2 = client.get('/ports')

    assert r1.status_code == 200
    assert r2.status_code == 429
