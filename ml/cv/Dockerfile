FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --upgrade pip setuptools wheel uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir \
    "fastapi>=0.115" "uvicorn[standard]" \
    "onnxruntime>=1.20" "opencv-python-headless>=4.10" \
    "mediapipe>=0.10" numpy prometheus-client structlog
# pip is only needed at build time and vendors its own outdated copies of urllib3/msgpack.
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
    /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12
COPY . .
EXPOSE 8003
CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8003"]
