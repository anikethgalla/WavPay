"""Pydantic schemas for request validation and API responses."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class BiometricStatus(str, Enum):
    MATCH_FOUND = "MATCH_FOUND"
    NO_MATCH = "NO_MATCH"
    LOW_QUALITY = "LOW_QUALITY"
    ENROLLED = "ENROLLED"
    BUSY = "BUSY"
    ERROR = "ERROR"


# -------------------------------------------------------------
# User Schemas
# -------------------------------------------------------------
class UserBase(BaseModel):
    user_id: str = Field(..., description="Unique alphanumeric user identifier (e.g. USR001)")
    name: str = Field(..., min_length=1, max_length=128, description="Full name of user")
    email: Optional[str] = Field(None, max_length=128)


class UserCreate(UserBase):
    pass


class StartEnrollmentRequest(BaseModel):
    user_id: str = Field(..., description="Unique User ID to enroll")
    name: str = Field(..., description="Full Name of User")
    email: Optional[str] = Field(None, description="Optional Email")


class UserResponse(UserBase):
    id: int
    active: bool
    created_at: datetime
    templates_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class UserEnrollResponse(BaseModel):
    status: str = "ENROLLED"
    user_id: str
    name: str
    templates_stored: int
    message: str


# -------------------------------------------------------------
# Biometric Schemas
# -------------------------------------------------------------
class BiometricScanResponse(BaseModel):
    status: BiometricStatus
    user_id: Optional[str] = None
    name: Optional[str] = None
    confidence: Optional[float] = None
    message: Optional[str] = None


class BiometricLatestResponse(BaseModel):
    event_id: Optional[str] = None
    status: BiometricStatus = BiometricStatus.NO_MATCH
    user_id: Optional[str] = None
    name: Optional[str] = None
    confidence: Optional[float] = None
    message: Optional[str] = None
    timestamp: Optional[datetime] = None


# -------------------------------------------------------------
# Payment Schemas
# -------------------------------------------------------------
class OrderCreateRequest(BaseModel):
    user_id: str = Field(..., description="ID of the biometrically verified user")
    amount: float = Field(..., gt=0, le=100000, description="Amount in INR (e.g. 100.00)")


class OrderCreateResponse(BaseModel):
    order_id: str
    razorpay_order_id: str
    amount: int  # in paise
    currency: str = "INR"
    key_id: str
    user_id: str
    user_name: str


class PaymentVerifyRequest(BaseModel):
    razorpay_order_id: str = Field(..., description="Razorpay Order ID")
    razorpay_payment_id: str = Field(..., description="Razorpay Payment ID")
    razorpay_signature: str = Field(..., description="HMAC-SHA256 signature from Razorpay")


class PaymentVerifyResponse(BaseModel):
    status: str  # SUCCESS, FAILED
    payment_id: Optional[str] = None
    order_id: str
    amount: float  # in INR
    message: str


class PaymentResponse(BaseModel):
    id: int
    user_id: str
    razorpay_order_id: str
    razorpay_payment_id: Optional[str]
    amount_inr: float
    currency: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
