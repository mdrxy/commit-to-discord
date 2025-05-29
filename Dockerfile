FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . . 

# Install pgrep for healthcheck
RUN apt-get update \
    && apt-get install -y procps \
    && rm -rf /var/lib/apt/lists/*

# Healthcheck to verify the commit_watcher process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f commit_watcher.py || exit 1

CMD ["python", "-u", "commit_watcher.py"]