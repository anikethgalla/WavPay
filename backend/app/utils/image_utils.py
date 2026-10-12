"""Image processing utilities, quality verification, and feature serialization."""

import io
from datetime import datetime
from pathlib import Path
from typing import Tuple
import cv2
import numpy as np
from app.config import DEBUG_DIR, settings


def validate_image_quality(image: np.ndarray) -> Tuple[bool, str]:
    """Validates if the captured image has sufficient quality and lighting for biometric processing.

    Returns:
        (is_valid, reason_or_status)
    """
    if image is None or image.size == 0:
        return False, "EMPTY_FRAME"

    h, w = image.shape[:2]
    if h < 64 or w < 64:
        return False, "FRAME_TOO_SMALL"

    # Convert to grayscale for illumination & contrast analysis
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    mean_brightness = float(np.mean(gray))
    std_contrast = float(np.std(gray))

    # Brightness checks
    if mean_brightness < 20.0:
        return False, "TOO_DARK"
    if mean_brightness > 245.0:
        return False, "TOO_BRIGHT"

    # Contrast check
    if std_contrast < 15.0:
        return False, "INSUFFICIENT_CONTRAST"

    return True, "QUALITY_OK"


def save_debug_image(image: np.ndarray, prefix: str = "scan") -> str:
    """Saves a debug frame to disk if STORE_DEBUG_IMAGES is enabled."""
    if not settings.STORE_DEBUG_IMAGES:
        return ""
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{timestamp}.jpg"
    filepath = DEBUG_DIR / filename
    cv2.imwrite(str(filepath), image)
    return str(filepath)


def serialize_features(features: np.ndarray) -> bytes:
    """Serializes a float32 NumPy feature vector into binary format."""
    buf = io.BytesIO()
    np.save(buf, features.astype(np.float32), allow_pickle=False)
    return buf.getvalue()


def deserialize_features(data: bytes) -> np.ndarray:
    """Deserializes binary bytes back into a NumPy float32 feature vector."""
    buf = io.BytesIO(data)
    return np.load(buf, allow_pickle=False)
