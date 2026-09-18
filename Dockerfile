FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends restic && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY scripts ./scripts
COPY templates ./templates
COPY static ./static
RUN useradd --uid 10001 --create-home appuser && mkdir -p /data /backups && chown appuser:appuser /data /backups
USER appuser
ARG RELEASE_SHA=local
ENV RELEASE_SHA=$RELEASE_SHA DATABASE_PATH=/data/reachmark.sqlite3 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz',timeout=4)"
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app"]
