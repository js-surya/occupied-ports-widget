# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2026-10-25

### Changed
- Compact Glance layout with eight initially visible ports, theme-colored exposure dots, total/public counts, and a Show all control.
- Briefly highlight newly detected ports while respecting reduced-motion preferences.

### Added
- Reusable Glance widget configuration and an additive `public_count` API field.

## [1.2.1] - 2026-10-25

### Added
- Optional Glance script to refresh port widgets automatically every three seconds, preserving collapse state and indicating refresh failures.

### Changed
- Default Docker discovery cache reduced from five seconds to one second for quicker start/stop updates.

### Fixed
- Replaced deployment-specific addresses in README examples and tests with illustrative values.
- Corrected the security policy to describe support for released versions.

## [1.2.0] - 2026-10-25

### Added
- Configurable `FRAME_ANCESTORS` policy for embedding the HTML widget.
- Regression coverage for cache concurrency, upstream failures, iframe policy, and polling.

### Fixed
- Widget framing no longer blocked by an unconditional `X-Frame-Options: DENY`.
- Polling preserves expanded/collapsed state and reverse-proxy URL prefixes.
- Serialize cache refreshes and use one threaded Gunicorn worker for consistent recent ordering.
- Expire inactive rate-limit entries when the minute window changes.
- README documents working Docker networking, browser iframe URLs, authenticated polling, and discovery limits.

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
