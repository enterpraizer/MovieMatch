import os
from functools import lru_cache
from typing import Any

import numpy as np
import onnxruntime as ort
import structlog

CLASSES = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

EMOTION_TO_GENRES: dict[str, list[str]] = {
    "angry": ["Action", "Thriller", "Crime", "War"],
    "disgust": ["Documentary", "Crime", "Mystery"],
    "fear": ["Horror", "Thriller", "Mystery", "Psychological"],
    "happy": ["Comedy", "Adventure", "Animation", "Family", "Romance"],
    "neutral": ["Drama", "Mystery", "Biography", "Comedy"],
    "sad": ["Drama", "Romance", "Biography", "Music"],
    "surprise": ["Sci-Fi", "Fantasy", "Adventure", "Mystery"],
}

EMOTION_MESSAGES: dict[str, str] = {
    "angry": "Channel that energy into something intense!",
    "disgust": "Something thought-provoking might help.",
    "fear": "Lean into the tension...",
    "happy": "You are in a great mood — let us keep it going!",
    "neutral": "Open to anything? Here is what is worth watching.",
    "sad": "A good story might be exactly what you need.",
    "surprise": "Ready for something amazing?",
}


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


@lru_cache(maxsize=1)
def _get_session() -> ort.InferenceSession:
    model_path = os.environ.get("ONNX_MODEL_PATH", "../models/emotion_model.onnx")

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    opts.inter_op_num_threads = 2
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    session = ort.InferenceSession(
        model_path,
        sess_options=opts,
        providers=["CPUExecutionProvider"],
    )

    input_info = session.get_inputs()[0]
    structlog.get_logger().info(
        "onnx_model_loaded",
        path=model_path,
        input_name=input_info.name,
        input_shape=input_info.shape,
    )
    return session


def predict_emotion(face_array: np.ndarray) -> dict[str, Any]:
    """Run emotion inference on a (1, 3, 224, 224) float32 tensor.

    NEVER logs face_array contents.
    """
    session = _get_session()
    input_name = session.get_inputs()[0].name

    raw_output = session.run(None, {input_name: face_array})[0]
    logits = np.asarray(raw_output).reshape(-1)[: len(CLASSES)]
    probs = _softmax(logits)

    top_idx = int(np.argmax(probs))
    emotion = CLASSES[top_idx]

    return {
        "emotion": emotion,
        "confidence": round(float(probs[top_idx]), 4),
        "all_scores": {c: round(float(p), 4) for c, p in zip(CLASSES, probs)},
        "genres": EMOTION_TO_GENRES[emotion],
        "message": EMOTION_MESSAGES[emotion],
    }
