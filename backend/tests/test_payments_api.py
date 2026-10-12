"""Integration tests for payment order creation and Razorpay signature verification."""

import cv2
import pytest
from app.config import settings
from app.utils.security import verify_razorpay_signature
from tests.test_palm_processing import create_synthetic_palm_image


def test_payment_lifecycle(client):
    """Verifies end-to-end payment flow:

    1. User enrollment
    2. Order creation
    3. Signature verification (valid vs invalid)
    4. Duplicate verification handling
    5. Payment query
    """
    # 1. Enroll user
    palm_img = create_synthetic_palm_image()
    _, buffer = cv2.imencode(".jpg", palm_img)
    client.post(
        "/api/users/enroll",
        data={"user_id": "USR777", "name": "Payment Tester", "email": "test@payment.com"},
        files={"file": ("palm.jpg", buffer.tobytes(), "image/jpeg")}
    )

    # 2. Create Order for ₹250.00
    order_res = client.post(
        "/api/payments/create-order",
        json={"user_id": "USR777", "amount": 250.00}
    )
    assert order_res.status_code == 200
    order_data = order_res.json()
    assert order_data["amount"] == 25000  # 250.00 INR in paise
    assert order_data["currency"] == "INR"
    assert "razorpay_order_id" in order_data
    order_id = order_data["razorpay_order_id"]

    # 3. Test Invalid Signature Verification
    invalid_verify_res = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": "pay_test_fake_123",
            "razorpay_signature": "invalid_fake_signature"
        }
    )
    assert invalid_verify_res.status_code == 400

    # 4. Test Valid Signature Verification
    payment_id = "pay_test_valid_999"
    # Generate authentic HMAC-SHA256 signature
    import hashlib
    import hmac
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    valid_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg,
        hashlib.sha256
    ).hexdigest()

    valid_verify_res = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_signature
        }
    )
    assert valid_verify_res.status_code == 200
    verify_data = valid_verify_res.json()
    assert verify_data["status"] == "SUCCESS"
    assert verify_data["amount"] == 250.00

    # 5. Test Duplicate Verification (Idempotency)
    dup_res = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": valid_signature
        }
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "SUCCESS"

    # 6. Retrieve Payment by Payment ID
    get_res = client.get(f"/api/payments/{payment_id}")
    assert get_res.status_code == 200
    pdata = get_res.json()
    assert pdata["user_id"] == "USR777"
    assert pdata["status"] == "SUCCESS"
    assert pdata["amount_inr"] == 250.00


def test_create_order_invalid_amount(client):
    """Verifies that invalid payment amounts are rejected."""
    # Amount <= 0
    res = client.post("/api/payments/create-order", json={"user_id": "USR777", "amount": 0})
    assert res.status_code in [400, 422]

    # Exceeding limit
    res_high = client.post("/api/payments/create-order", json={"user_id": "USR777", "amount": 999999})
    assert res_high.status_code in [400, 422]
