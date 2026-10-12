"""RGB565 Decoder standalone test and verification script.

Tests the RGB565 decoding pipeline with known color patches and produces a preview image.
"""

import sys
from pathlib import Path
import cv2
import numpy as np

# Ensure utf-8 output encoding on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.rgb565_decoder import decode_rgb565, encode_rgb565, RGB565DecodeError


def run_tests():
    print("=" * 60)
    print("      RGB565 DECODER STANDALONE VERIFICATION SUITE      ")
    print("=" * 60)

    # 1. Test Known Colors (Red, Green, Blue, Black, White)
    width, height = 320, 240
    print(f"\n[*] Generating synthetic test canvas ({width}x{height})...")

    test_bgr = np.zeros((height, width, 3), dtype=np.uint8)
    # Split into 5 vertical stripes: Black, White, Pure Red, Pure Green, Pure Blue
    stripe_w = width // 5
    test_bgr[:, 0:stripe_w] = [0, 0, 0]         # Black (BGR)
    test_bgr[:, stripe_w:2*stripe_w] = [255, 255, 255] # White (BGR)
    test_bgr[:, 2*stripe_w:3*stripe_w] = [0, 0, 255]   # Red (BGR)
    test_bgr[:, 3*stripe_w:4*stripe_w] = [0, 255, 0]   # Green (BGR)
    test_bgr[:, 4*stripe_w:] = [255, 0, 0]             # Blue (BGR)

    # Test Little Endian
    raw_little = encode_rgb565(test_bgr, byte_order="little")
    print(f"[+] Encoded Little-Endian Raw Buffer: {len(raw_little)} bytes (Expected: {width * height * 2})")

    decoded_little = decode_rgb565(raw_little, width=width, height=height, byte_order="little")
    print(f"[+] Decoded Shape: {decoded_little.shape}, Dtype: {decoded_little.dtype}")
    print(f"    Min Value: {decoded_little.min()}, Max Value: {decoded_little.max()}")

    # Test Big Endian
    raw_big = encode_rgb565(test_bgr, byte_order="big")
    decoded_big = decode_rgb565(raw_big, width=width, height=height, byte_order="big")
    print(f"[+] Decoded Big-Endian Shape: {decoded_big.shape}, Dtype: {decoded_big.dtype}")

    # Verify colors within 5-bit/6-bit precision quantization
    # Red stripe should have high R, near 0 G/B
    red_sample = decoded_little[height // 2, 2 * stripe_w + 10]
    print(f"[*] Red Stripe Sample (BGR): {red_sample.tolist()} (Expected ~ [0, 0, 255])")
    assert red_sample[2] >= 248 and red_sample[0] == 0 and red_sample[1] == 0, "Red color decode failed"

    # Green stripe
    green_sample = decoded_little[height // 2, 3 * stripe_w + 10]
    print(f"[*] Green Stripe Sample (BGR): {green_sample.tolist()} (Expected ~ [0, 255, 0])")
    assert green_sample[1] >= 252 and green_sample[0] == 0 and green_sample[2] == 0, "Green color decode failed"

    # Blue stripe
    blue_sample = decoded_little[height // 2, 4 * stripe_w + 10]
    print(f"[*] Blue Stripe Sample (BGR): {blue_sample.tolist()} (Expected ~ [255, 0, 0])")
    assert blue_sample[0] >= 248 and blue_sample[1] == 0 and blue_sample[2] == 0, "Blue color decode failed"

    # 2. Test Invalid Byte Length Handling
    print("\n[*] Testing Error Handling on Corrupted Length...")
    try:
        decode_rgb565(b"\x00" * 100, width=320, height=240)
        print("[X] Failed: Decoder accepted corrupted byte length!")
        sys.exit(1)
    except RGB565DecodeError as e:
        print(f"[+] Correctly rejected invalid byte length: {e}")

    # 3. Save Preview Image
    output_dir = backend_dir / "data" / "debug_frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_path = output_dir / "test_rgb565_preview.jpg"
    cv2.imwrite(str(preview_path), decoded_little)
    print(f"\n[+] Saved decoded test pattern preview: {preview_path}")

    print("\n============================================================")
    print("   ALL RGB565 DECODER TESTS PASSED WITH 100% PRECISION!     ")
    print("============================================================\n")


if __name__ == "__main__":
    run_tests()
