FROM python:3.11-slim
WORKDIR /app

# Update package lists, install dependencies (including procps for healthcheck),
# and then clean up in a single layer to keep the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv and project dependencies
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync

COPY . .

# Healthcheck to verify the commit_watcher process is running
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f commit_watcher.py || exit 1

CMD ["uv", "run", "python", "-u", "commit_watcher.py"]