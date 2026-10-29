# Recipe Hugging Face follows to build and run our server.
FROM python:3.13-slim

# uv installs the exact package versions recorded in uv.lock
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Hugging Face runs the container as user 1000: keep the database in /tmp,
# which is writable. It is recreated with the 8 demo customers on startup.
ENV PORT=8000 \
    SINISTRE_DB=/tmp/claims.db \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD [".venv/bin/python", "-m", "mcp_server.server"]
