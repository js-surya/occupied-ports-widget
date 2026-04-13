from unittest.mock import patch

import app as app_module
from app import app


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
            app_module._CACHE['payload'] = None
            app_module._CACHE['ts'] = 0
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
            app_module._CACHE['payload'] = None
            app_module._CACHE['ts'] = 0
            client = app.test_client()
            response = client.get('/ports')

    assert response.status_code == 200
    assert response.json['ok'] is True
    ports = [item['port'] for item in response.json['items']]
    assert ports == [8088, 3001]
