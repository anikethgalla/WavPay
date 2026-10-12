"""Unit tests for palm quality validation, feature extraction, and template comparison."""

import cv2
import numpy as np
import pytest
from app.services.palm_processor import OpenCVPalmFeatureExtractor
from app.utils.image_utils import deserialize_features, serialize_features, validate_image_quality


def create_synthetic_palm_image(w=320, h=240, skin_bgr=(140, 170, 210), line_pattern=1) -> np.ndarray:
    """Generates a synthetic palm-like hand image for deterministic testing."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Background is dark table/desk
    img[:, :] = [30, 30, 30]

    # Draw palm base (ellipse)
    center = (w // 2, h // 2 + 10)
    axes = (60, 70)
    cv2.ellipse(img, center, axes, 0, 0, 360, skin_bgr, -1)

    # Draw 5 fingers
    finger_offsets = [(-45, -50), (-25, -70), (0, -75), (25, -70), (45, -50)]
    for fx, fy in finger_offsets:
        cv2.line(img, center, (center[0] + fx, center[1] + fy), skin_bgr, 20)

    # Draw palm creases (principal lines)
    line_color = (int(skin_bgr[0] * 0.7), int(skin_bgr[1] * 0.7), int(skin_bgr[2] * 0.7))
    if line_pattern == 1:
        cv2.line(img, (center[0] - 30, center[1] - 10), (center[0] + 30, center[1] - 15), line_color, 2)
        cv2.line(img, (center[0] - 25, center[1] + 10), (center[0] + 25, center[1] + 15), line_color, 2)
    else:
        cv2.line(img, (center[0] - 35, center[1] - 20), (center[0] + 20, center[1] + 10), line_color, 3)
        cv2.line(img, (center[0] - 15, center[1] + 25), (center[0] + 35, center[1] - 5), line_color, 2)

    return img


def test_validate_image_quality():
    """Verifies image quality validation checks."""
    # Empty
    is_valid, reason = validate_image_quality(np.array([]))
    assert not is_valid
    assert reason == "EMPTY_FRAME"

    # Too dark
    dark_img = np.zeros((240, 320, 3), dtype=np.uint8) + 10
    is_valid, reason = validate_image_quality(dark_img)
    assert not is_valid
    assert reason == "TOO_DARK"

    # Too bright
    bright_img = np.ones((240, 320, 3), dtype=np.uint8) * 250
    is_valid, reason = validate_image_quality(bright_img)
    assert not is_valid
    assert reason == "TOO_BRIGHT"

    # Valid synthetic palm
    palm_img = create_synthetic_palm_image()
    is_valid, reason = validate_image_quality(palm_img)
    assert is_valid
    assert reason == "QUALITY_OK"


def test_palm_feature_extractor():
    """Verifies feature extraction and L2 normalization."""
    extractor = OpenCVPalmFeatureExtractor(roi_size=128)
    palm1 = create_synthetic_palm_image(line_pattern=1)

    features1 = extractor.extract(palm1)
    assert features1 is not None
    assert features1.dtype == np.float32
    assert len(features1) > 0

    # L2 Norm should be ~ 1.0
    norm = np.linalg.norm(features1)
    assert pytest.approx(norm, abs=1e-4) == 1.0

    # Same image must yield similarity of 1.0
    features1_duplicate = extractor.extract(palm1)
    sim_same = float(np.dot(features1, features1_duplicate))
    assert pytest.approx(sim_same, abs=1e-4) == 1.0

    # Different palm pattern should yield lower similarity
    palm2 = create_synthetic_palm_image(line_pattern=2)
    features2 = extractor.extract(palm2)
    assert features2 is not None
    sim_diff = float(np.dot(features1, features2))
    assert sim_diff < 0.98


def test_feature_serialization_roundtrip():
    """Verifies serialization and deserialization of float32 feature vectors."""
    vec = np.random.randn(256).astype(np.float32)
    vec = vec / np.linalg.norm(vec)

    raw_bytes = serialize_features(vec)
    reconstructed = deserialize_features(raw_bytes)

    assert reconstructed.shape == vec.shape
    assert reconstructed.dtype == np.float32
    assert np.allclose(vec, reconstructed)
