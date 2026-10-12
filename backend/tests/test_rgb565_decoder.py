"""Unit tests for RGB565 byte decoder service."""

import numpy as np
import pytest
from app.services.rgb565_decoder import RGB565DecodeError, decode_rgb565, encode_rgb565


def test_rgb565_exact_size_qvga():
    """Verifies that exactly 153,600 bytes are accepted for 320x240 RGB565."""
    width, height = 320, 240
    raw = bytes(width * height * 2)
    bgr = decode_rgb565(raw, width=width, height=height, byte_order="little")
    assert bgr.shape == (height, width, 3)
    assert bgr.dtype == np.uint8
    assert np.all(bgr == 0)


def test_rgb565_rejects_invalid_size():
    """Verifies that invalid buffer sizes are rejected with RGB565DecodeError."""
    with pytest.raises(RGB565DecodeError):
        decode_rgb565(b"\x00" * 153599, width=320, height=240)

    with pytest.raises(RGB565DecodeError):
        decode_rgb565(b"\x00" * 153601, width=320, height=240)


def test_rgb565_known_colors_little_endian():
    """Verifies color channel mapping for Black, White, Red, Green, Blue in Little Endian."""
    h, w = 10, 10
    # Red: R5=31 (0x1F), G6=0, B5=0 -> 0xF800 -> Little Endian: bytes [0x00, 0xF8]
    red_pixel_le = bytes([0x00, 0xF8]) * (w * h)
    red_bgr = decode_rgb565(red_pixel_le, width=w, height=h, byte_order="little")
    assert red_bgr[0, 0, 2] == 255  # Red channel
    assert red_bgr[0, 0, 1] == 0    # Green channel
    assert red_bgr[0, 0, 0] == 0    # Blue channel

    # Green: R5=0, G6=63 (0x3F), B5=0 -> 0x07E0 -> Little Endian: bytes [0xE0, 0x07]
    green_pixel_le = bytes([0xE0, 0x07]) * (w * h)
    green_bgr = decode_rgb565(green_pixel_le, width=w, height=h, byte_order="little")
    assert green_bgr[0, 0, 1] == 255  # Green
    assert green_bgr[0, 0, 0] == 0
    assert green_bgr[0, 0, 2] == 0

    # Blue: R5=0, G6=0, B5=31 (0x1F) -> 0x001F -> Little Endian: bytes [0x1F, 0x00]
    blue_pixel_le = bytes([0x1F, 0x00]) * (w * h)
    blue_bgr = decode_rgb565(blue_pixel_le, width=w, height=h, byte_order="little")
    assert blue_bgr[0, 0, 0] == 255  # Blue
    assert blue_bgr[0, 0, 1] == 0
    assert blue_bgr[0, 0, 2] == 0

    # White: 0xFFFF -> bytes [0xFF, 0xFF]
    white_pixel = bytes([0xFF, 0xFF]) * (w * h)
    white_bgr = decode_rgb565(white_pixel, width=w, height=h, byte_order="little")
    assert np.all(white_bgr == 255)


def test_rgb565_roundtrip_encode_decode():
    """Verifies that encoding a BGR image to RGB565 and decoding it back preserves colors."""
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    img[:, :] = [180, 120, 200]  # Random color (B, G, R)

    encoded = encode_rgb565(img, byte_order="little")
    decoded = decode_rgb565(encoded, width=50, height=50, byte_order="little")

    # Due to 5-bit/6-bit quantization, maximum error per channel should be <= 8
    diff = np.abs(img.astype(int) - decoded.astype(int))
    assert np.max(diff) <= 8
