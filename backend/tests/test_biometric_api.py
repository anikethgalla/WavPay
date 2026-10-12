"""Integration tests for ESP32 raw RGB565 scan endpoint and polling."""

import cv2
import numpy as np
import pytest
from app.config import settings
from app.services.rgb565_decoder import encode_rgb565
from tests.test_palm_processing import create_synthetic_palm_image


def test_health_check(client):
    """Verifies GET /health returns OK."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "HEALTHY"


def test_esp32_scan_unauthorized(client):
    """Verifies that missing or invalid X-Device-Key is rejected with 401."""
    res = client.post(
        "/api/biometric/scan",
        content=b"\x00" * (320 * 240 * 2),
        headers={"X-Device-Key": "invalid_wrong_key"}
    )
    assert res.status_code == 401


def test_esp32_scan_invalid_format_header(client):
    """Verifies that unsupported pixel format returns 400."""
    res = client.post(
        "/api/biometric/scan",
        content=b"\x00" * 100,
        headers={
            "X-Device-Key": settings.DEVICE_API_KEY,
            "X-Pixel-Format": "JPEG"  # Only RGB565 is allowed
        }
    )
    assert res.status_code == 400
    assert "Unsupported pixel format" in res.json()["detail"]


def test_esp32_scan_invalid_size(client):
    """Verifies that payload size mismatch returns 400."""
    res = client.post(
        "/api/biometric/scan",
        content=b"\x00" * 100,
        headers={
            "X-Device-Key": settings.DEVICE_API_KEY,
            "X-Pixel-Format": "RGB565",
            "X-Image-Width": "320",
            "X-Image-Height": "240"
        }
    )
    assert res.status_code == 400
    assert "Payload size mismatch" in res.json()["detail"]


def test_esp32_scan_flow_enroll_and_match(client):
    """Tests the full end-to-end cycle:

    1. Enroll a user with a palm image.
    2. Stream identical raw RGB565 frame from ESP32.
    3. Verify MATCH_FOUND response.
    """
    palm_img = create_synthetic_palm_image(w=320, h=240, line_pattern=1)
    raw_rgb565 = encode_rgb565(palm_img, byte_order="big")

    # 1. Enroll User USR100
    enroll_res = client.post(
        "/api/users/enroll",
        data={"user_id": "USR100", "name": "Aniketh Galla", "email": "aniketh@example.com"},
        files={"file": ("palm.raw", raw_rgb565, "application/octet-stream")}
    )
    assert enroll_res.status_code == 200
    assert enroll_res.json()["status"] == "ENROLLED"

    # 2. ESP32 Scans the same palm in raw RGB565
    scan_res = client.post(
        "/api/biometric/scan",
        content=raw_rgb565,
        headers={
            "X-Device-Key": settings.DEVICE_API_KEY,
            "X-Pixel-Format": "RGB565",
            "X-Image-Width": "320",
            "X-Image-Height": "240"
        }
    )
    assert scan_res.status_code == 200
    data = scan_res.json()
    assert data["status"] == "MATCH_FOUND"
    assert data["user_id"] == "USR100"
    assert data["name"] == "Aniketh Galla"
    assert data["confidence"] >= settings.MATCH_THRESHOLD

    # 3. Check /api/biometric/latest polling endpoint
    latest_res = client.get("/api/biometric/latest")
    assert latest_res.status_code == 200
    latest_data = latest_res.json()
    assert latest_data["status"] == "MATCH_FOUND"
    assert latest_data["user_id"] == "USR100"
