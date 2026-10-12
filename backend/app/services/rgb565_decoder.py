"""RGB565 to BGR OpenCV image decoder service.

Handles conversion of raw 16-bit RGB565 byte streams from ESP32-CAM into
standard 8-bit BGR NumPy arrays compatible with OpenCV.
"""

from typing import Literal
import numpy as np


class RGB565DecodeError(ValueError):
    """Raised when RGB565 byte stream is invalid or corrupted."""
    pass


def decode_rgb565(
    data: bytes,
    width: int = 320,
    height: int = 240,
    byte_order: Literal["little", "big"] = "big" # Default to 'big' for ESP32-CAM DMA output
) -> np.ndarray:
    """Decodes raw RGB565 bytes into an OpenCV BGR uint8 array of shape (height, width, 3).

    Args:
        data: Raw RGB565 byte buffer from camera.
        width: Image width in pixels (e.g. 320 for QVGA).
        height: Image height in pixels (e.g. 240 for QVGA).
        byte_order: 'big' (default for ESP32-CAM DMA) or 'little' endian.

    Returns:
        numpy.ndarray: Shape (height, width, 3), dtype uint8, in OpenCV BGR format.

    Raises:
        RGB565DecodeError: If data length does not match width * height * 2.
    """
    expected_bytes = width * height * 2
    if len(data) != expected_bytes:
        raise RGB565DecodeError(
            f"Invalid RGB565 data length: received {len(data)} bytes, expected {expected_bytes} bytes "
            f"for {width}x{height} resolution."
        )

    # ESP32-CAM DVP outputs High Byte first (RRRRRGGG), then Low Byte (GGGBBBBB)
    dt = np.dtype(">u2") if byte_order == "big" else np.dtype("<u2")

    # Read into 2D uint16 array
    pixels = np.frombuffer(data, dtype=dt).reshape((height, width))

    # Extract 5-bit Red, 6-bit Green, 5-bit Blue components
    # Format: RRRRR GGGGGG BBBBB
    r5 = (pixels >> 11) & 0x1F
    g6 = (pixels >> 5) & 0x3F
    b5 = pixels & 0x1F

    # Scale 5-bit and 6-bit components to full 8-bit [0-255] range
    r8 = ((r5 << 3) | (r5 >> 2)).astype(np.uint8)
    g8 = ((g6 << 2) | (g6 >> 4)).astype(np.uint8)
    b8 = ((b5 << 3) | (b5 >> 2)).astype(np.uint8)

    # Stack channels into OpenCV BGR order
    bgr_image = np.dstack((b8, g8, r8))
    return bgr_image


def encode_rgb565(
    bgr_image: np.ndarray,
    byte_order: Literal["little", "big"] = "big"
) -> bytes:
    """Encodes an OpenCV BGR uint8 image into raw RGB565 bytes."""
    if bgr_image.ndim != 3 or bgr_image.shape[2] != 3:
        raise ValueError("Image must have shape (H, W, 3).")

    b8 = bgr_image[:, :, 0].astype(np.uint16)
    g8 = bgr_image[:, :, 1].astype(np.uint16)
    r8 = bgr_image[:, :, 2].astype(np.uint16)

    r5 = (r8 >> 3) & 0x1F
    g6 = (g8 >> 2) & 0x3F
    b5 = (b8 >> 3) & 0x1F

    pixels = (r5 << 11) | (g6 << 5) | b5
    dt = np.dtype(">u2") if byte_order == "big" else np.dtype("<u2")
    return pixels.astype(dt).tobytes()
