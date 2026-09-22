# ASTRAEUS API image (P5-B).
#
# Runtime only: the package plus the `api` extra (FastAPI/uvicorn/PyJWT).
# Scientific backends (wotan, transitleastsquares) are REQUIRED deps, so
# a built image always has a functioning TLS gate — never the fail-open
# container PRD §4.2 warns about. `batman` stays out (DEC-LIC: optional).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ASTRAEUS_SINGLE_USER=1 \
    ASTRAEUS_DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY astraeus/ ./astraeus/
RUN pip install --no-cache-dir --retries 10 --timeout 120 ".[api]" && \
    python -m astraeus --version && \
    python -m astraeus capabilities

VOLUME ["/data"]
EXPOSE 8000
# Bind 0.0.0.0: inside the container the loopback is the container's own;
# Caddy (same compose network) is the only ingress. Never publish 8000
# directly on a public host.
CMD ["astraeus-api", "--host", "0.0.0.0", "--port", "8000"]
