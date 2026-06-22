# Occupied Ports Widget for Glance

![CI](https://github.com/js-surya/occupied-ports-widget/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

A tiny helper service that exposes **currently published Docker host ports** as JSON for a Glance widget.

It is useful when you are about to deploy a new service and want a quick, human-friendly view of which host ports are already occupied — and whether they are exposed on **loopback**, **Tailscale**, **private LAN**, or **all interfaces/public**.

---

## Screenshot

![Occupied Ports Widget](assets/occupied-ports-widget.jpg)

---

## Features

- Dynamic port discovery from running Docker containers
- Deduplicated by **host port** with protocol aggregation
- Exposure metadata per port:
  - `host_ips`
  - `primary_host_ip`
  - `exposure_scope`
  - `exposure_scopes`
  - `private_ports`
- Optional source-container reporting with `SHOW_SOURCE=true`
- Sorting modes: `asc`, `desc`, `recent`
- Port range filter (`MIN_PORT`, `MAX_PORT`)
- Reserved port hints in payload (for example `22`, `53`, `80`, `443`)
- Clickable links per port (`LINK_SCHEME://LINK_HOST:port`)
- JSON API (`/ports`) and ready-made HTML widget (`/widget`)
- Optional token auth and rate limiting for safer public use
- Production-oriented runtime (Gunicorn, non-root user, healthcheck)
- CI with tests and Docker build verification

---

## API shape

Example `GET /ports` response:

```json
{
  "ok": true,
  "error": "",
  "sort_mode": "asc",
  "min_port": 1,
  "max_port": 65535,
  "count": 2,
  "items": [
    {
      "port": 53,
      "proto": "tcp",
      "protocols": ["tcp", "udp"],
      "url": "https://example.com:53",
      "reserved": true,
      "reserved_label": "DNS",
      "primary_host_ip": "100.78.209.116",
      "host_ips": ["100.78.209.116", "127.0.0.1"],
      "exposure_scope": "mixed",
      "exposure_scopes": ["tailscale", "loopback"],
      "private_ports": [53],
      "source": "glance, pihole",
      "sources": ["glance", "pihole"],
      "source_count": 2
    },
    {
      "port": 8088,
      "proto": "tcp",
      "protocols": ["tcp"],
      "url": "https://example.com:8088",
      "reserved": false,
      "reserved_label": "",
      "primary_host_ip": "127.0.0.1",
      "host_ips": ["127.0.0.1"],
      "exposure_scope": "loopback",
      "exposure_scopes": ["loopback"],
      "private_ports": [8080]
    }
  ]
}
```

### Exposure scope meanings

- `public` → bound to `0.0.0.0` / `::`
- `tailscale` → bound to Tailscale address range
- `private` → bound to RFC1918/private non-loopback address
- `loopback` → bound to `127.0.0.1` / `::1`
- `mixed` → the same host port is published on multiple scopes
- `unknown` → bind address could not be classified

---

## Endpoints

- `GET /health`
- `GET /ports`
- `GET /widget`

`/ports` is the structured API for Glance `custom-api` templates.

`/widget` is a ready-made HTML view that includes:
- scope-aware chip styling
- hover tooltips with bind IPs, protocols, and sources
- lightweight auto-refresh polling

---

## Quick start

```bash
git clone https://github.com/js-surya/occupied-ports-widget.git
cd occupied-ports-widget
docker compose up -d --build
curl http://127.0.0.1:8789/health
curl http://127.0.0.1:8789/ports
```

Expected:

- `/health` returns `{"ok": true}`
- `/ports` returns JSON with `ok`, `count`, and `items`

---

## Docker Compose

The included compose file uses:

- loopback-only bind for the widget: `127.0.0.1:8789:8789`
- pinned socket proxy image: `tecnativa/docker-socket-proxy:v0.4.2`
- restricted Docker API scope: `CONTAINERS=1`, `POST=0`

Start it with:

```bash
docker compose up -d --build
```

---

## Configuration

Environment variables:

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

### Most useful options

- `SHOW_SOURCE=true` → include container names in API and widget tooltips
- `LINK_HOST=your-domain-or-ip` → make links point somewhere meaningful
- `AUTH_ENABLED=true` + `WIDGET_TOKEN=...` → required if exposed beyond private access
- `RATE_LIMIT_PER_MINUTE=30` → safer for public/reverse-proxied deployments

---

## Glance examples

### Minimal `custom-api` example

```yaml
- type: custom-api
  title: Occupied Ports
  cache: 10s
  url: http://host.docker.internal:8789/ports
  template: |
    <ul class="list">
      {{ range .JSON.Array "items" }}
        <li>{{ .Int "port" }}</li>
      {{ end }}
    </ul>
```

### Recommended `custom-api` example with scope hints

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
        display: block;
        text-align: center;
        padding: 0.28rem 0.2rem;
        border-radius: 6px;
        border: 1px solid color-mix(in srgb, var(--color-text-base) 16%, transparent);
        background: color-mix(in srgb, var(--color-widget-background) 82%, var(--color-text-base) 18%);
        font-size: 1rem;
        font-weight: 600;
        color: var(--color-text-base);
        text-decoration: none;
      }
      .port-chip.public { border-color: color-mix(in srgb, #ff7b72 46%, transparent); }
      .port-chip.tailscale { border-color: color-mix(in srgb, #6eb6ff 46%, transparent); }
      .port-chip.private { border-color: color-mix(in srgb, #f2cc60 42%, transparent); }
      .port-chip.loopback { border-color: color-mix(in srgb, #3fb950 42%, transparent); }
      .port-chip.mixed { border-style: dashed; }
      .port-chip.reserved {
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
            <a
              class="port-chip {{ .String "exposure_scope" }} {{ if .Bool "reserved" }}reserved{{ end }}"
              href="{{ .String "url" }}"
              target="_blank"
              rel="noreferrer"
              title="{{ .String "exposure_scope" }} · {{ .String "primary_host_ip" }}"
            >
              {{ .Int "port" }}
            </a>
          </li>
        {{ end }}
      </ul>
    {{ end }}
```

### Ready-made iframe widget example

If you prefer using the built-in HTML widget instead of writing a template:

```yaml
- type: iframe
  title: Occupied Ports
  source: http://host.docker.internal:8789/widget
  height: 220
```

> If `host.docker.internal` is not reachable in your setup, replace it with a host address reachable from inside the Glance container.

---

## Public-safe deployment

If anyone on the internet may reach this helper, treat it as sensitive operational metadata.

Recommended minimums:

1. Keep the container bound to loopback only:
   ```yaml
   ports:
     - "127.0.0.1:8789:8789"
   ```
2. Put it behind HTTPS reverse proxy
3. Enable token auth:
   ```yaml
   environment:
     AUTH_ENABLED: true
     WIDGET_TOKEN: change-me-long-random-token
   ```
4. Lower rate limit:
   ```yaml
   environment:
     RATE_LIMIT_PER_MINUTE: 30
   ```
5. Use `TRUST_PROXY=true` only when actually behind a trusted reverse proxy
6. Consider `SHOW_SOURCE=false` if you do not want to reveal container names

A typical public-safe env block:

```yaml
environment:
  LINK_SCHEME: https
  LINK_HOST: your-public-host.example.com
  AUTH_ENABLED: true
  WIDGET_TOKEN: change-me-long-random-token
  RATE_LIMIT_PER_MINUTE: 30
  DEBUG_ERRORS: false
  TRUST_PROXY: true
  SHOW_SOURCE: true
ports:
  - "127.0.0.1:8789:8789"
```

If your reverse proxy supports it, have it send `X-Widget-Token` to the upstream request.

---

## Security notes

- Docker socket access is sensitive. This project uses [`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy) with minimal allowed scope.
- The default compose bind is loopback-only to avoid accidental public exposure.
- Optional token auth is supported via `AUTH_ENABLED=true` and request header `X-Widget-Token`.
- Error responses are sanitized by default with `DEBUG_ERRORS=false`.
- Published ports can reveal meaningful details about your stack; expose carefully.

---

## Development

Run tests locally:

```bash
pytest -q
```

Build test:

```bash
docker build -t occupied-ports-widget:local .
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT
