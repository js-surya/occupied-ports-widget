# Security Policy

## Supported versions

This project is currently pre-1.x and only the latest `master` branch is supported for security fixes.

## Reporting a vulnerability

Please do **not** open public issues for security vulnerabilities.

Instead, report privately via GitHub security advisory (preferred) or direct maintainer contact.
Include:

- Affected version/commit
- Reproduction steps
- Impact assessment
- Suggested remediation (if available)

## Hardening guidance

If deploying outside a private tailnet/network:

1. Run behind HTTPS reverse proxy
2. Enable `AUTH_ENABLED=true` and set strong `WIDGET_TOKEN`
3. Set lower `RATE_LIMIT_PER_MINUTE` (e.g., 30)
4. Keep `DEBUG_ERRORS=false`
5. Restrict inbound IPs where possible
6. Do not widen Docker socket proxy permissions beyond required scope
