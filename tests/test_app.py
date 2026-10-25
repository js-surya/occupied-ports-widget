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
                {'IP': '100.64.0.10', 'PublicPort': 53, 'PrivatePort': 53, 'Type': 'udp'},
            ],
        },
        {
            'Names': ['/pihole'],
            'Ports': [
                {'IP': '127.0.0.1', 'PublicPort': 53, 'PrivatePort': 53, 'Type': 'tcp'},
                {'IP': '100.64.0.10', 'PublicPort': 53, 'PrivatePort': 53, 'Type': 'tcp'},
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
    assert dns_item['host_ips'] == ['100.64.0.10', '127.0.0.1']
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


def test_widget_frame_policy_and_api_headers():
    with patch.object(app_module, 'FRAME_ANCESTORS', 'https://glance.example.com'), patch.object(app_module, '_get_payload', return_value={'ok': True, 'items': [], 'count': 0}):
        client = app.test_client()
        response = client.get('/widget')
        assert response.headers['Content-Security-Policy'] == 'frame-ancestors https://glance.example.com'
        assert 'X-Frame-Options' not in response.headers
        assert client.get('/health').headers['X-Frame-Options'] == 'DENY'


def test_upstream_error_is_sanitized_and_cached():
    _reset_cache()
    with patch('app.requests.get', side_effect=RuntimeError('secret upstream detail')) as upstream, patch.object(app_module, 'DEBUG_ERRORS', False), patch.object(app_module, 'CACHE_SECONDS', 60):
        client = app.test_client()
        first = client.get('/ports').json
        second = client.get('/ports').json
    assert first == second
    assert first['ok'] is False
    assert first['error'] == 'temporarily unavailable'
    assert first['items'] == []
    assert upstream.call_count == 1


def test_concurrent_requests_share_one_cache_refresh():
    from concurrent.futures import ThreadPoolExecutor
    import time

    _reset_cache()
    def fetch():
        time.sleep(0.02)
        return {'ok': True, 'items': [], 'count': 0}

    with patch.object(app_module, '_fetch_ports', side_effect=fetch) as upstream, patch.object(app_module, 'CACHE_SECONDS', 60):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: app_module._get_payload(), range(8)))
    assert all(result['ok'] for result in results)
    assert upstream.call_count == 1


def test_old_rate_limit_entries_expire():
    _reset_cache()
    app_module._RATE['old-client'] = {'window': -1, 'count': 120}
    with app.test_request_context('/ports'):
        assert app_module._check_rate_limit()
    assert 'old-client' not in app_module._RATE


def test_empty_docker_response_is_success():
    _reset_cache()
    with patch('app.requests.get') as upstream:
        upstream.return_value.json.return_value = []
        payload = app.test_client().get('/ports').json
    assert payload['ok'] is True
    assert payload['count'] == 0
    assert payload['items'] == []


def test_recent_order_is_stable_across_refreshes():
    _reset_cache()
    def container(port):
        return {'Ports': [{'PublicPort': port, 'Type': 'tcp'}]}

    with patch('app.requests.get') as upstream, patch.object(app_module, 'SORT_MODE', 'recent'), patch.object(app_module, 'CACHE_SECONDS', 0):
        upstream.return_value.json.return_value = [container(8080), container(9000)]
        client = app.test_client()
        assert [i['port'] for i in client.get('/ports').json['items']] == [9000, 8080]
        upstream.return_value.json.return_value = [container(8080), container(9000), container(5000)]
        assert [i['port'] for i in client.get('/ports').json['items']] == [5000, 9000, 8080]


def test_started_and_stopped_container_ports_follow_cache_expiry():
    _reset_cache()
    running = [{'Ports': [{'PublicPort': 18080, 'PrivatePort': 8080, 'Type': 'tcp'}]}]
    with patch('app.requests.get') as upstream, patch.object(app_module, 'CACHE_SECONDS', 1), patch('app.time.monotonic', return_value=100) as clock:
        upstream.return_value.json.return_value = []
        client = app.test_client()
        assert client.get('/ports').json['items'] == []
        upstream.return_value.json.return_value = running
        clock.return_value = 102
        assert [i['port'] for i in client.get('/ports').json['items']] == [18080]
        upstream.return_value.json.return_value = []
        clock.return_value = 102.5
        assert [i['port'] for i in client.get('/ports').json['items']] == [18080]
        clock.return_value = 104
        assert client.get('/ports').json['items'] == []
