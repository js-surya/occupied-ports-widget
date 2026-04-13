# Changelog

All notable changes to this project will be documented in this file.

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
