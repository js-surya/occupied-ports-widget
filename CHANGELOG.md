# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-06-22

### Added
- Exposure metadata per published port: `host_ips`, `primary_host_ip`, `exposure_scope`, `exposure_scopes`, and `private_ports`
- Protocol aggregation via `protocols` while keeping backward-compatible `proto`
- Optional multi-container source reporting via `SHOW_SOURCE=true` with `source`, `sources`, and `source_count`
- Scope-aware `/widget` styling and tooltips for quick public/private/tailscale visibility
- Test coverage for `/widget`, exposure metadata, auth, and rate limiting

### Changed
- Pinned `tecnativa/docker-socket-proxy` compose image to `v0.4.2`
- Simplified README examples and clarified private vs public deployment guidance

## [1.0.0] - 2026-04-13

### Added
- Initial Occupied Ports widget helper for Glance
- Docker socket proxy integration (`CONTAINERS=1`, `POST=0`)
- Port dedupe by port number and numeric sorting
- Clickable port links
- Reserved-port hints
- Sorting modes (`asc`, `desc`, `recent`)
- Port range filtering (`MIN_PORT`, `MAX_PORT`)
- Response status envelope (`ok`, `error`, `count`)
- Container hardening defaults and healthcheck
- Optional token auth (`X-Widget-Token`) and rate limiting
- CI workflow with tests + Docker build
- README docs, screenshot, and acknowledgements
- SECURITY.md policy
