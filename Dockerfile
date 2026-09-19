# Reachmark — production image.
# Base pinned by digest (python:3.13-slim, digested 2026-09-19 from Docker Hub).
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends restic && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Test files, sources and caches stay out of the image (see .dockerignore).
COPY *.py ./
COPY scripts ./scripts
COPY templates ./templates
COPY static ./static

# Run as an unprivileged user; data and backups live on mounted volumes.
RUN useradd --create-home --uid 10001 reachmark \
    && mkdir -p /data /backups \
    && chown -R reachmark:reachmark /data /backups /app
USER reachmark

ARG RELEASE_SHA=local
ENV RELEASE_SHA=$RELEASE_SHA DATABASE_PATH=/data/reachmark.sqlite3 PORT=8000 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz',timeout=4)"
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app"]
