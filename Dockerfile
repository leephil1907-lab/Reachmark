FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py services.py enquiries.py portfolio.py operations.py mcp_transport.py maps.py map_provider.py ./
COPY templates ./templates
COPY static ./static
RUN useradd --create-home appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser
ENV DATABASE_PATH=/data/sitegap.sqlite3 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=4)"
CMD ["gunicorn","--bind","0.0.0.0:8000","--workers","1","--threads","4","--timeout","120","app:app"]
