from unittest.mock import patch

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
        client = app.test_client()
        response = client.get('/ports')

    assert response.status_code == 200
    assert response.json == {
        'items': [
            {'port': 53, 'proto': 'udp'},
            {'port': 3001, 'proto': 'tcp'},
            {'port': 8088, 'proto': 'tcp'},
        ]
    }
