# Build from the repository root:   docker build -f api/Dockerfile -t presales-tools:v4 .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ARTIFACT_ROOT=/data/artifacts

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY api api
COPY integration integration
COPY tools tools
COPY master master

# The entrypoint starts as root only to fix ownership of a mounted disk (Render disks mount root-owned),
# then drops to the unprivileged "app" user before the server starts.
RUN useradd --create-home app && mkdir -p /data/artifacts && chown -R app /data /app \
    && chmod +x /app/api/docker-entrypoint.sh
VOLUME ["/data/artifacts"]
EXPOSE 8080

# The server listens on $PORT (Render sets it; default 8080). WEB_CONCURRENCY = number of workers (default 2).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8080')).status == 200 else 1)"

# API_KEYS, LINK_SECRET and PUBLIC_BASE_URL must be provided at run time (see api/.env.example).
ENTRYPOINT ["/app/api/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec python -m uvicorn api.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --no-access-log"]
