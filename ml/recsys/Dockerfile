FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir --upgrade pip setuptools wheel uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --index-strategy unsafe-best-match \
    "fastapi>=0.115" "uvicorn[standard]" \
    "torch>=2.5" "pytorch-lightning>=2.4" \
    "asyncpg>=0.30" "mlflow>=2.18" \
    numpy prometheus-client structlog python-dotenv
# pip is only needed at build time and vendors its own outdated copies of urllib3/msgpack.
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
    /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12
COPY . .
EXPOSE 8001
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
