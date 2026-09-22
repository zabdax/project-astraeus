BUCKET: P5-B
STATUS: COMPLETE (image builds; compose config verified)

PROVIDES:
- `Dockerfile` (3.12-slim, `.[api]`, required science backends baked
  in so the TLS gate cannot fail open; `batman` excluded per DEC-LIC;
  `/data` volume; binds 0.0.0.0 only inside the compose network).
- `docker-compose.yml` (fail-closed `${ASTRAEUS_API_KEY:?}`,
  health-gated Caddy dependency, named volumes).
- `Caddyfile` (sole ingress on :80, gzip, reverse_proxy api:8000).
- `.dockerignore` (slim context: no tests/docs/caches/runs).

CONSUMED BY:
- Operators deploying a cold host (`docker compose up --build -d`)

MEASURED:
- `docker compose config --quiet`: green.
- Image builds from the committed tree (see logbook).
- Container smoke: `/health` + submit→COMPLETED (see logbook).

FILES OF INTEREST:
- Dockerfile, docker-compose.yml, Caddyfile, .dockerignore

KNOWN CONSTRAINTS:
- No TLS termination in Caddyfile (loopback/dev default); production
  HTTPS is operator config (domain + `tls` directive), not committed.
- Fly/Hetzner specifics intentionally left to the operator: compose
  covers any single Docker host.

NEXT REQUIRED ACTION:
- P5-C closes credibility; final full gate closes the project.
