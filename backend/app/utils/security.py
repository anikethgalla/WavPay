"""Security utilities for API key verification and Razorpay signature validation."""

import hashlib
import hmac
import secrets


def hash_api_key(api_key: str) -> str:
    """Computes SHA-256 hash of API key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, expected_hash: str) -> bool:
    """Constant-time verification of raw API key against stored hash."""
    computed_hash = hash_api_key(raw_key)
    return hmac.compare_digest(computed_hash, expected_hash)


def verify_razorpay_signature(
    order_id: str,
    payment_id: str,
    signature: str,
    secret: str
) -> bool:
    """Verifies Razorpay payment signature using server-side HMAC-SHA256 calculation.

    Formula: HMAC_SHA256(order_id + "|" + payment_id, secret)
    """
    if not order_id or not payment_id or not signature or not secret:
        return False
    
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    generated_signature = hmac.new(
        secret.encode("utf-8"),
        msg,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(generated_signature, signature)


def generate_event_id() -> str:
    """Generates a secure random event identifier."""
    return secrets.token_hex(16)
