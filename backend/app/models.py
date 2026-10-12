"""SQLAlchemy database ORM models."""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """User account model for biometric authentication and payments."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    email = Column(String(128), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    templates = relationship("PalmTemplate", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user")


class PalmTemplate(Base):
    """Biometric feature vector template for enrolled palms."""
    __tablename__ = "palm_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    template = Column(LargeBinary, nullable=False)  # Serialized NumPy float32 feature array
    version = Column(String(32), default="opencv_gabor_v1", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="templates")


class Payment(Base):
    """Payment transaction records linked to users and Razorpay orders."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    razorpay_order_id = Column(String(128), unique=True, index=True, nullable=False)
    razorpay_payment_id = Column(String(128), index=True, nullable=True)
    amount = Column(Integer, nullable=False)  # Amount in paise (1 INR = 100 paise)
    currency = Column(String(10), default="INR", nullable=False)
    status = Column(String(32), default="CREATED", nullable=False)  # CREATED, SUCCESS, FAILED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="payments")


class Device(Base):
    """Authorized hardware scanning devices (ESP32-CAM)."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(64), unique=True, index=True, nullable=False)
    api_key_hash = Column(String(128), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class BiometricScanEvent(Base):
    """Recent biometric scan events for frontend polling and session tracking."""
    __tablename__ = "biometric_scan_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    status = Column(String(32), nullable=False)  # MATCH_FOUND, NO_MATCH, LOW_QUALITY, ERROR
    user_id = Column(String(64), nullable=True)
    user_name = Column(String(128), nullable=True)
    confidence = Column(Float, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
