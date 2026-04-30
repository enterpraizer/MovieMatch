FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    fastapi>=0.115 uvicorn[standard] \
    sentence-transformers>=3.3 asyncpg>=0.30 \
    prometheus-client structlog python-dotenv
COPY . .
EXPOSE 8002
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
