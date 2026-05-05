import cv2
import numpy as np
import structlog

VIT_MEAN = np.array([0.5, 0.5, 0.5], dtype=np.float32)
VIT_STD = np.array([0.5, 0.5, 0.5], dtype=np.float32)
TARGET_SIZE = 224
FACE_PADDING = 0.07
MIN_FACE_SIZE = 15

_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
_face_cascade = cv2.CascadeClassifier(_CASCADE_PATH)
if _face_cascade.empty():
    raise RuntimeError(f"Failed to load Haar cascade at {_CASCADE_PATH}")


def preprocess_image_bytes(image_bytes: bytes) -> np.ndarray | None:
    """PRIVACY CONTRACT: bytes are processed in RAM only, never written or logged.

    Returns (1, 3, 224, 224) float32 ONNX-ready array, or None if no face found.
    """
    logger = structlog.get_logger()

    nparr = np.frombuffer(image_bytes, dtype=np.uint8)
    if nparr.size == 0:
        logger.warning("image_empty_buffer")
        return None

    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        logger.warning("image_decode_failed")
        return None

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=4,
        minSize=(30, 30),
    )
    if len(faces) == 0:
        logger.info("no_face_detected", image_wh=f"{w}x{h}")
        return None

    fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    confidence = 1.0
    pad_x = int(fw * FACE_PADDING)
    pad_y = int(fh * FACE_PADDING)
    x1 = max(0, fx - pad_x)
    y1 = max(0, fy - pad_y)
    x2 = min(w, fx + fw + pad_x)
    y2 = min(h, fy + fh + pad_y)

    crop_w, crop_h = x2 - x1, y2 - y1
    if crop_w < MIN_FACE_SIZE or crop_h < MIN_FACE_SIZE:
        logger.info("face_crop_too_small", crop=f"{crop_w}x{crop_h}")
        return None

    face = img_rgb[y1:y2, x1:x2]
    face = cv2.resize(face, (TARGET_SIZE, TARGET_SIZE), interpolation=cv2.INTER_LINEAR)
    face = face.astype(np.float32) / 255.0
    face = (face - VIT_MEAN) / VIT_STD

    face = np.expand_dims(face.transpose(2, 0, 1), axis=0)

    logger.info(
        "face_preprocessed",
        face_confidence=round(float(confidence), 3),
        face_size=f"{crop_w}x{crop_h}",
        image_size=f"{w}x{h}",
    )
    return face.astype(np.float32)
