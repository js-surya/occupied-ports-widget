# Occupied Ports Widget for Glance

![CI](https://github.com/js-surya/occupied-ports-widget/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

A tiny helper service that exposes **currently published Docker host ports** as JSON for a Glance `custom-api` widget.

This is useful when you are about to deploy a new service and want a quick visual list of ports already in use.

---

## Screenshot

![Occupied Ports Widget](assets/occupied-ports-widget.jpg)

---

## Features

- Dynamic port discovery from running Docker containers
- Deduplicated by **port number** (protocol variants collapsed)
- Sorting modes: `asc`, `desc`, `recent`
- Port range filter (`MIN_PORT`, `MAX_PORT`)
- Reserved port hints in payload (e.g. 22/53/80/443)
- Clickable links per port (`LINK_SCHEME://LINK_HOST:port`)
- Status envelope (`ok`, `error`, `count`) for safer widget rendering
- Production-oriented runtime (Gunicorn, non-root user, healthcheck)
- Basic CI with tests + Docker build check (GitHub Actions)
- Works well with Glance `custom-api` widgets

---

## How it works

- `occupied-ports-widget` calls Docker Engine API via a restricted `docker-socket-proxy`
- It reads running containers and collects `PublicPort` mappings
- It returns JSON in this shape:

```json
{
  "ok": true,
  "error": "",
  "sort_mode": "asc",
  "min_port": 1,
  "max_port": 65535,
  "count": 2,
  "items": [
    { "port": 53, "proto": "tcp", "url": "http://localhost:53", "reserved": true, "reserved_label": "DNS" },
    { "port": 8088, "proto": "tcp", "url": "http://localhost:8088", "reserved": false, "reserved_label": "" }
  ]
}
```

---

## Run with Docker Compose

```bash
docker compose up -d --build
```

> Note: the compose file currently uses `tecnativa/docker-socket-proxy:latest` because a previously pinned tag was unavailable on Docker Hub. If you prefer stricter reproducibility, pin this image to a verified published tag or digest in your own deployment.

Helper API:

- `GET /health`
- `GET /ports`

Local test:

```bash
curl http://127.0.0.1:8789/ports
```

---

## Detailed installation

### 1) Clone the repository

```bash
git clone https://github.com/js-surya/occupied-ports-widget.git
cd occupied-ports-widget
```

### 2) Review/update runtime settings

Edit `docker-compose.yml` under `occupied-ports-widget.environment`.
Most important keys:

- `LINK_HOST` → host/domain used for clickable links in the widget payload
- `LINK_SCHEME` → usually `http` for private use, `https` when published through TLS
- `AUTH_ENABLED` / `WIDGET_TOKEN` → required if exposing beyond private tailnet
- `RATE_LIMIT_PER_MINUTE` → reduce if public-facing (e.g., `30`)

### 3) Start the service

```bash
docker compose up -d --build
```

### 4) Verify health and data endpoints

```bash
curl http://127.0.0.1:8789/health
curl http://127.0.0.1:8789/ports
```

Expected:

- `/health` returns `{"ok":true}`
- `/ports` returns JSON with `ok`, `count`, and `items`

### 5) Add widget to Glance

Use either the **Minimal** or **Styled** template from the next section and paste it into your `glance.yml`.

### 6) Restart Glance

```bash
docker compose -f /path/to/glance/docker-compose.yml down
docker compose -f /path/to/glance/docker-compose.yml up -d
```

### 7) Troubleshooting quick checks

```bash
docker logs occupied-ports-widget --tail 100
docker logs occupied-ports-docker-proxy --tail 100
curl http://127.0.0.1:8789/ports
```

If Glance cannot reach `http://host.docker.internal:8789/ports`, replace it with a reachable host address for your Docker setup. On Linux, `host.docker.internal` may require extra configuration or a different reachable host/IP.

---

## Glance configuration

### 1) Minimal template

```yaml
- type: custom-api
  title: Occupied Ports
  cache: 15s
  url: http://host.docker.internal:8789/ports
  template: |
    <ul class="list">
      {{ range .JSON.Array "items" }}
        <li>{{ .Int "port" }}</li>
      {{ end }}
    </ul>
```

### 2) Styled template (dark/light adaptive + clickable)

```yaml
- type: custom-api
  title: Occupied Ports
  cache: 15s
  url: http://host.docker.internal:8789/ports
  template: |
    <style>
      .ports-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.4rem;
      }
      .ports-grid > li {
        list-style: none;
        margin: 0;
      }
      .port-chip {
        text-align: center;
        padding: 0.28rem 0.2rem;
        border-radius: 6px;
        border: 1px solid color-mix(in srgb, var(--color-text-base) 16%, transparent);
        background: color-mix(in srgb, var(--color-widget-background) 82%, var(--color-text-base) 18%);
        font-size: 1rem;
        font-weight: 600;
        color: var(--color-text-base);
        opacity: 0.97;
        display: block;
        transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
      }
      .port-chip:hover {
        background: color-mix(in srgb, var(--color-widget-background) 72%, var(--color-primary) 28%);
        border-color: color-mix(in srgb, var(--color-primary) 45%, transparent);
      }
      .port-chip.reserved {
        border-color: color-mix(in srgb, var(--color-primary) 42%, transparent);
        background: color-mix(in srgb, var(--color-widget-background) 75%, var(--color-primary) 25%);
        color: var(--color-primary);
      }
    </style>
    {{ if not (.JSON.Bool "ok") }}
      <div class="color-negative size-h5">Data unavailable</div>
      <div class="color-subdue">{{ .JSON.String "error" }}</div>
    {{ else }}
      <ul class="list ports-grid collapsible-container" data-collapse-after="16">
        {{ range .JSON.Array "items" }}
          <li>
            <a class="port-chip {{ if .Bool "reserved" }}reserved{{ end }}" href="{{ .String "url" }}" target="_blank" rel="noreferrer">
              {{ .Int "port" }}
            </a>
          </li>
        {{ end }}
      </ul>
    {{ end }}
```

> If `host.docker.internal` is not reachable in your setup, replace with a reachable host address from inside the Glance container.

---

## Compatibility

- Tested with Linux Docker Engine 29.x
- Tested with Glance dashboard using `custom-api` widgets

---

## Configuration

Environment variables (optional):

- `PORT` (default: `8789`)
- `DOCKER_API` (default: `http://occupied-ports-docker-proxy:2375/containers/json`)
- `TIMEOUT_SECONDS` (default: `6`)
- `CACHE_SECONDS` (default: `5`)
- `MIN_PORT` / `MAX_PORT` (defaults: `1` / `65535`)
- `SORT_MODE` (`asc` | `desc` | `recent`, default: `asc`)
- `SHOW_SOURCE` (`true|false`, default: `false`)
- `LINK_SCHEME` (default: `http`)
- `LINK_HOST` (default: `localhost`)
- `AUTH_ENABLED` (`true|false`, default: `false`)
- `WIDGET_TOKEN` (required when `AUTH_ENABLED=true`)
- `RATE_LIMIT_PER_MINUTE` (default: `120`)
- `DEBUG_ERRORS` (`true|false`, default: `false`)
- `TRUST_PROXY` (`true|false`, default: `false`)

---

## Public-safe preset (recommended)

If this service is exposed beyond a private tailnet, use:

```yaml
environment:
  LINK_SCHEME: https
  LINK_HOST: your-public-host.example.com
  AUTH_ENABLED: true
  WIDGET_TOKEN: change-me-long-random-token
  RATE_LIMIT_PER_MINUTE: 30
  DEBUG_ERRORS: false
  TRUST_PROXY: true   # only when behind reverse proxy
ports:
  - "127.0.0.1:8789:8789"
```

And configure your reverse proxy to send `X-Widget-Token` for the Glance request.

---

## Security notes

- Docker socket access is sensitive. This project uses [`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy) with minimal allowed scope (`CONTAINERS=1`, `POST=0`).
- Container hardening defaults are enabled: non-root runtime, read-only filesystem, `no-new-privileges`, dropped Linux capabilities, memory/CPU/pid limits.
- The default compose bind is loopback-only (`127.0.0.1:8789:8789`) to avoid accidental public exposure.
- Optional API token auth is supported via `AUTH_ENABLED=true` + `WIDGET_TOKEN` and request header `X-Widget-Token`.
- Basic per-IP rate limiting is enabled (configurable via `RATE_LIMIT_PER_MINUTE`).
- Error responses are sanitized by default (`DEBUG_ERRORS=false`) to avoid leaking internals.
- Published ports are operational metadata. Treat this service as sensitive even if container names are hidden.
- Recommended for public exposure: place behind reverse proxy + TLS + IP allowlist and enable auth token.

---

## Development

Run tests locally:

```bash
pytest -q
```

---

## Acknowledgements

### AI-assisted development

This project was created with AI assistance (OpenClaw + GPT-based coding help) and reviewed/adjusted by the maintainer.

### Upstream/open-source projects used

- [`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy) — restricted Docker API proxy used for safer Docker socket access.
- [`Flask`](https://github.com/pallets/flask) — lightweight Python web framework for the helper API.
- [`Requests`](https://github.com/psf/requests) — HTTP client used to query Docker API endpoints.
- [`Glance`](https://github.com/glanceapp/glance) — dashboard that renders this helper via `custom-api` widget.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

---

## License

MIT
