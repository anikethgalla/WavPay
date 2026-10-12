"""User management and palm biometric enrollment API endpoints."""

import logging
from typing import Optional, Dict
import cv2
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import PalmTemplate, User
from app.schemas import StartEnrollmentRequest, UserEnrollResponse, UserResponse
from app.services.palm_processor import palm_extractor
from app.utils.image_utils import (
    save_debug_image,
    serialize_features,
    validate_image_quality,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["Users & Enrollment"])

# Global in-memory state for pending hardware camera enrollment
pending_enrollment: Dict[str, Optional[str]] = {
    "user_id": None,
    "name": None,
    "email": None,
}


@router.post("/start-enrollment")
def start_hardware_enrollment(req: StartEnrollmentRequest):
    """Arms the system to treat the NEXT ESP32-CAM palm scan as an enrollment capture for this user."""
    pending_enrollment["user_id"] = req.user_id.strip()
    pending_enrollment["name"] = req.name.strip()
    pending_enrollment["email"] = req.email.strip() if req.email else None

    logger.info(f"Armed hardware enrollment for: {pending_enrollment['name']} ({pending_enrollment['user_id']})")
    return {
        "status": "ARMED",
        "user_id": req.user_id,
        "name": req.name,
        "message": "Ready! Place palm over the ESP32-CAM to capture and save the reference template."
    }


@router.get("/enrollment-status")
def get_enrollment_status():
    """Checks if a hardware enrollment session is currently pending."""
    return {
        "is_armed": pending_enrollment["user_id"] is not None,
        "pending_user": pending_enrollment
    }


@router.post("/cancel-enrollment")
def cancel_hardware_enrollment():
    """Cancels any pending hardware enrollment."""
    pending_enrollment["user_id"] = None
    pending_enrollment["name"] = None
    pending_enrollment["email"] = None
    return {"status": "CANCELLED"}


@router.post("/enroll", response_model=UserEnrollResponse)
async def enroll_user_palm(
    user_id: str = Form(..., description="Unique User ID (e.g. USR001)"),
    name: str = Form(..., description="Full Name of the User"),
    email: Optional[str] = Form(None, description="Email address"),
    file: UploadFile = File(..., description="Palm image file (JPEG, PNG) or raw 153600-byte RGB565"),
    db: Session = Depends(get_db),
):
    """Manual enrollment with file upload (for fallback or testing)."""
    content = await file.read()

    # Determine if uploaded file is raw RGB565 bytes (153600 bytes) or standard image file
    if len(content) == 320 * 240 * 2:
        from app.services.rgb565_decoder import decode_rgb565
        image = decode_rgb565(content, width=320, height=240, byte_order="big")
    else:
        nparr = np.frombuffer(content, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to decode image. Provide a valid JPEG/PNG or raw 320x240 RGB565 buffer."
        )

    save_debug_image(image, prefix=f"enroll_{user_id}")

    # 1. Image Quality Validation
    is_valid_quality, reason = validate_image_quality(image)
    if not is_valid_quality:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Image quality check failed: {reason}. Ensure adequate lighting and contrast."
        )

    # 2. Extract Biometric Palm Features
    features = palm_extractor.extract(image)
    if features is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Palm not detected in the provided image. Place your entire palm open in center frame."
        )

    # 3. Create or update User record
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        user = User(user_id=user_id, name=name, email=email, active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.name = name
        if email:
            user.email = email
        user.active = True
        db.commit()

    # 4. Store Serialized Biometric Template
    serialized_template = serialize_features(features)
    palm_template = PalmTemplate(
        user_id=user.user_id,
        template=serialized_template,
        version="opencv_gabor_v1"
    )
    db.add(palm_template)
    db.commit()

    templates_count = db.query(PalmTemplate).filter(PalmTemplate.user_id == user.user_id).count()

    return UserEnrollResponse(
        status="ENROLLED",
        user_id=user.user_id,
        name=user.name,
        templates_stored=templates_count,
        message=f"Biometric template for '{user.name}' ({user.user_id}) enrolled successfully."
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user_profile(user_id: str, db: Session = Depends(get_db)):
    """Fetches user details and template enrollment count."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    templates_count = db.query(PalmTemplate).filter(PalmTemplate.user_id == user.user_id).count()
    return UserResponse(
        id=user.id,
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        active=user.active,
        created_at=user.created_at,
        templates_count=templates_count
    )


@router.delete("/{user_id}/biometric")
def delete_user_biometric(user_id: str, db: Session = Depends(get_db)):
    """Deletes all biometric templates for a user (Privacy & GDPR compliance)."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    deleted_count = db.query(PalmTemplate).filter(PalmTemplate.user_id == user_id).delete()
    db.commit()

    return {
        "status": "DELETED",
        "user_id": user_id,
        "templates_deleted": deleted_count,
        "message": f"All biometric data for user '{user_id}' has been permanently purged."
    }
