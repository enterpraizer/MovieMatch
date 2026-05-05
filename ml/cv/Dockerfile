FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    fastapi>=0.115 uvicorn[standard] \
    onnxruntime>=1.20 opencv-python-headless>=4.10 \
    mediapipe>=0.10 numpy prometheus-client structlog
COPY . .
EXPOSE 8003
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8003"]
