FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir --upgrade pip setuptools wheel uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]" \
    "sentence-transformers>=3.3" "asyncpg>=0.30" \
    prometheus-client structlog python-dotenv
# pip is only needed at build time and vendors its own outdated copies of urllib3/msgpack.
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
    /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12
COPY . .
EXPOSE 8002
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2"]
