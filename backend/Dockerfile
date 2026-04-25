# Stage 1: base — shared foundation
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 curl build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app

# Stage 2: deps — install all Python packages
FROM base AS deps
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir -e ".[dev]"

# Stage 3: development — adds hot reload
FROM deps AS development
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 4: production — minimal, non-root, no dev tools
FROM base AS production
RUN groupadd -r -g 1001 app && useradd -r -u 1001 -g app app
COPY --from=deps /usr/local/lib/python3.12/site-packages/ \
    /usr/local/lib/python3.12/site-packages/
COPY --from=deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=deps /usr/local/bin/alembic /usr/local/bin/alembic
COPY . .
RUN chown -R app:app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--loop", "uvloop", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
