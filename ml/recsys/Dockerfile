FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    fastapi>=0.115 uvicorn[standard] \
    torch>=2.5 pytorch-lightning>=2.4 \
    asyncpg>=0.30 mlflow>=2.18 \
    numpy prometheus-client structlog python-dotenv
COPY . .
EXPOSE 8001
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
