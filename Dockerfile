FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends restic && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY web ./web
COPY agents ./agents
COPY crew ./crew
COPY scripts ./scripts
COPY templates ./templates
COPY static ./static
# AI crew assets: vendored playbooks (attributed, unmodified), the facts-only
# knowledge base the receptionist answers from, and the offline demo fixtures.
COPY skills ./skills
COPY knowledge ./knowledge
COPY fixtures ./fixtures
RUN groupadd --system reachmark && useradd --system --gid reachmark --home-dir /app --no-create-home reachmark \
    && mkdir -p /data /backups \
    && chown -R reachmark:reachmark /app /data /backups
ARG RELEASE_SHA=local
ENV RELEASE_SHA=$RELEASE_SHA DATABASE_PATH=/data/reachmark.sqlite3 PORT=8000 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER reachmark
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz',timeout=4)"
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - web.app:app"]
