# Occupied Ports Widget for Glance

A tiny helper service that exposes **currently published Docker host ports** as JSON for a Glance `custom-api` widget.

This is useful when you are about to deploy a new service and want a quick visual list of ports already in use.

---

## Screenshot

![Occupied Ports Widget](assets/occupied-ports-widget.jpg)

---

## Features

- Dynamic port discovery from running Docker containers
- Deduplicated by **port number** (protocol variants collapsed)
- Sorted numeric output
- Lightweight Flask API (`/ports`)
- Works well with Glance `custom-api` widgets

---

## How it works

- `occupied-ports-widget` calls Docker Engine API via a restricted `docker-socket-proxy`
- It reads running containers and collects `PublicPort` mappings
- It returns JSON in this shape:

```json
{
  "items": [
    { "port": 53, "proto": "tcp" },
    { "port": 8088, "proto": "tcp" }
  ]
}
```

---

## Run with Docker Compose

```bash
docker compose up -d --build
```

Helper API:

- `GET /health`
- `GET /ports`

Local test:

```bash
curl http://127.0.0.1:8789/ports
```

---

## Glance configuration

Add this widget to your `glance.yml`:

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
        border: 1px solid color-mix(in srgb, var(--color-text-base) 14%, transparent);
        font-size: 1rem;
        font-weight: 600;
        color: var(--color-text-base);
        opacity: 0.95;
      }
    </style>
    <ul class="list ports-grid collapsible-container" data-collapse-after="16">
      {{ range .JSON.Array "items" }}
        <li><div class="port-chip">{{ .Int "port" }}</div></li>
      {{ end }}
    </ul>
```

> If `host.docker.internal` is not reachable in your setup, replace with a reachable host address from inside the Glance container.

---

## Configuration

Environment variables (optional):

- `PORT` (default: `8789`)
- `DOCKER_API` (default: `http://occupied-ports-docker-proxy:2375/containers/json`)
- `TIMEOUT_SECONDS` (default: `6`)

---

## Security notes

- Docker socket access is sensitive. This project uses [`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy) with minimal allowed scope (`CONTAINERS=1`, `POST=0`).
- Keep this service private (tailnet/private network), not publicly exposed.

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

## License

MIT
