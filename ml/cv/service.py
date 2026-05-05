import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import structlog
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from inferencer import CLASSES, _get_session, predict_emotion
from preprocess import preprocess_image_bytes

MAX_SIZE = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    structlog.get_logger().info("cv_service_starting")
    _get_session()
    structlog.get_logger().info("cv_service_ready")
    yield
    structlog.get_logger().info("cv_service_stopped")


app = FastAPI(title="MovieMatch CV Service", version="1.0.0", lifespan=lifespan)


class EmotionResponse(BaseModel):
    emotion: str
    confidence: float
    all_scores: dict[str, float]
    genres: list[str]
    message: str
    processing_ms: int


@app.post("/detect", response_model=EmotionResponse)
async def detect(image: UploadFile = File(...)) -> EmotionResponse:
    start = time.perf_counter()
    logger = structlog.get_logger()

    image_bytes = await image.read()
    face_array: Any = None
    try:
        if len(image_bytes) > MAX_SIZE:
            raise HTTPException(
                status_code=413,
                detail={"code": "IMAGE_TOO_LARGE", "message": "Max 5MB"},
            )

        face_array = preprocess_image_bytes(image_bytes)
    finally:
        del image_bytes

    if face_array is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FACE_NOT_DETECTED",
                "message": "No face found. Use a clear, well-lit photo of your face.",
            },
        )

    try:
        result = predict_emotion(face_array)
    finally:
        del face_array

    processing_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "emotion_detected",
        emotion=result["emotion"],
        confidence=result["confidence"],
        processing_ms=processing_ms,
    )
    return EmotionResponse(**result, processing_ms=processing_ms)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "supported_emotions": CLASSES}
