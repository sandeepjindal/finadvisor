# Single-container image. SQLite is embedded (no DB server); the brain persists on the
# mounted /data volume.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    DB_PATH=/data/brain.db

RUN pip install --no-cache-dir uv
WORKDIR /app

# Install deps first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --extra data --extra news --extra documents

# App code
COPY . .

VOLUME ["/data"]
CMD ["uv", "run", "--no-dev", "python", "app.py"]
