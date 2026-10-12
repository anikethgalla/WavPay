"""Biometric scanning, real-time live preview stream, and recognition API endpoints."""

import io
import logging
from typing import Optional
import cv2
import numpy as np
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    UploadFile,
    File,
    status,
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import BiometricScanEvent, Device, PalmTemplate, User
from app.schemas import BiometricLatestResponse, BiometricScanResponse, BiometricStatus
from app.services.palm_matcher import palm_matcher
from app.services.palm_processor import palm_extractor
from app.services.rgb565_decoder import RGB565DecodeError, decode_rgb565
from app.utils.image_utils import save_debug_image, serialize_features, validate_image_quality
from app.utils.security import generate_event_id, verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/biometric", tags=["Biometrics"])

# In-memory store for the latest decoded camera frame (JPEG bytes)
latest_frame_jpeg: Optional[bytes] = None

# Flag to pause biometric processing during active payment checkout
is_camera_processing_paused: bool = False


@router.post("/pause")
def set_camera_processing_pause(paused: bool = True):
    """Pauses or resumes biometric feature matching on incoming camera frames."""
    global is_camera_processing_paused
    is_camera_processing_paused = paused
    logger.info(f"[BIOMETRIC] Camera matching paused state set to: {is_camera_processing_paused}")
    return {"status": "OK", "is_paused": is_camera_processing_paused}


def set_latest_preview_frame(bgr_image: np.ndarray):
    """Encodes and stores the latest decoded BGR frame as JPEG for the web viewfinder."""
    global latest_frame_jpeg
    try:
        # Draw palm detection visualizer on preview if detected
        preview_img = bgr_image.copy()
        roi, contour = palm_extractor.segment_palm(preview_img)
        if contour is not None:
            cv2.drawContours(preview_img, [contour], -1, (0, 255, 0), 2)
            # Draw center crosshair
            h, w = preview_img.shape[:2]
            cv2.circle(preview_img, (w // 2, h // 2), 24, (0, 200, 255), 2)

        _, jpeg_buf = cv2.imencode(".jpg", preview_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        latest_frame_jpeg = jpeg_buf.tobytes()
    except Exception as e:
        logger.warning(f"Failed to generate preview JPEG: {e}")


def verify_device_authorization(x_device_key: Optional[str], db: Session) -> bool:
    """Verifies that the request comes from an authorized ESP32 hardware device."""
    if not x_device_key:
        return False

    if x_device_key == settings.DEVICE_API_KEY:
        return True

    devices = db.query(Device).filter(Device.active == True).all()
    for dev in devices:
        if verify_api_key(x_device_key, dev.api_key_hash):
            return True

    return False


@router.post("/scan", response_model=BiometricScanResponse)
async def scan_palm_esp32(
    request: Request,
    x_device_key: Optional[str] = Header(None, alias="X-Device-Key"),
    x_image_width: int = Header(320, alias="X-Image-Width"),
    x_image_height: int = Header(240, alias="X-Image-Height"),
    x_pixel_format: str = Header("RGB565", alias="X-Pixel-Format"),
    db: Session = Depends(get_db),
):
    """Primary high-speed endpoint for ESP32-CAM raw RGB565 stream."""
    # 1. Authenticate hardware device
    if not verify_device_authorization(x_device_key, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized scanner device key."
        )

    # 2. Validate format headers
    if x_pixel_format.upper() != "RGB565":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported pixel format: '{x_pixel_format}'. Expected 'RGB565'."
        )

    # 3. Read raw body bytes directly
    raw_body = await request.body()
    expected_size = x_image_width * x_image_height * 2

    if len(raw_body) != expected_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payload size mismatch: received {len(raw_body)} bytes, expected {expected_size} bytes."
        )

    # 3. Decode RGB565 to OpenCV BGR (ESP32-CAM DMA outputs Big-Endian byte order)
    try:
        bgr_frame = decode_rgb565(raw_body, width=x_image_width, height=x_image_height, byte_order="big")
    except RGB565DecodeError as e:
        logger.error(f"RGB565 decode failed: {e}")
        return BiometricScanResponse(status=BiometricStatus.ERROR, message="RGB565 frame decoding failed.")

    # 4. Update live dashboard viewfinder immediately
    set_latest_preview_frame(bgr_frame)
    save_debug_image(bgr_frame, prefix="scan_esp32")

    # If payment/order creation is active, don't send camera frame for biometric processing
    if is_camera_processing_paused:
        logger.info("[BIOMETRIC] Frame received but biometric processing is paused during active payment.")
        return BiometricScanResponse(
            status=BiometricStatus.BUSY,
            message="Payment in progress. Biometric processing paused."
        )

    # 5. Image Quality Check
    is_valid_quality, quality_reason = validate_image_quality(bgr_frame)
    if not is_valid_quality:
        _record_scan_event(db, status=BiometricStatus.LOW_QUALITY, message=quality_reason)
        return BiometricScanResponse(status=BiometricStatus.LOW_QUALITY, message=f"Low quality image: {quality_reason}")

    # 6. Palm Feature Extraction
    features = palm_extractor.extract(bgr_frame)
    if features is None:
        _record_scan_event(db, status=BiometricStatus.LOW_QUALITY, message="No palm contour or ROI detected.")
        return BiometricScanResponse(status=BiometricStatus.LOW_QUALITY, message="Palm not detected or positioned incorrectly.")

    # 7A. Check if in Live Hardware Enrollment Mode
    from app.api.users import pending_enrollment
    if pending_enrollment.get("user_id"):
        target_uid = pending_enrollment["user_id"]
        target_name = pending_enrollment["name"] or target_uid
        target_email = pending_enrollment.get("email")

        user = db.query(User).filter(User.user_id == target_uid).first()
        if not user:
            user = User(user_id=target_uid, name=target_name, email=target_email, active=True)
            db.add(user)
            db.commit()
            db.refresh(user)

        serialized_template = serialize_features(features)
        template_record = PalmTemplate(
            user_id=user.user_id,
            template=serialized_template,
            version="opencv_gabor_v1"
        )
        db.add(template_record)
        db.commit()

        pending_enrollment["user_id"] = None
        pending_enrollment["name"] = None
        pending_enrollment["email"] = None

        logger.info(f"[ENROLLMENT] Successfully enrolled {user.name} ({user.user_id}) from live camera scan!")

        _record_scan_event(
            db,
            status=BiometricStatus.ENROLLED,
            user_id=user.user_id,
            user_name=user.name,
            confidence=1.0,
            message="User enrolled successfully from live ESP32-CAM scan!"
        )

        return BiometricScanResponse(
            status=BiometricStatus.MATCH_FOUND,
            user_id=user.user_id,
            name=user.name,
            confidence=1.0,
            message="Palm enrolled successfully!"
        )

    # 7B. Biometric Matching
    matched_user, confidence, match_status = palm_matcher.match(features, db)

    if match_status == "MATCH_FOUND" and matched_user:
        _record_scan_event(
            db,
            status=BiometricStatus.MATCH_FOUND,
            user_id=matched_user.user_id,
            user_name=matched_user.name,
            confidence=confidence,
            message="User authenticated successfully."
        )
        return BiometricScanResponse(
            status=BiometricStatus.MATCH_FOUND,
            user_id=matched_user.user_id,
            name=matched_user.name,
            confidence=confidence,
            message="Palm matched successfully."
        )
    else:
        _record_scan_event(
            db,
            status=BiometricStatus.NO_MATCH,
            confidence=confidence,
            message="No matching palm template found."
        )
        return BiometricScanResponse(
            status=BiometricStatus.NO_MATCH,
            confidence=confidence,
            message="No match found for this palm."
        )


@router.get("/latest-frame")
def get_latest_camera_frame():
    """Returns the latest decoded camera frame as a JPEG image for the dashboard viewfinder."""
    global latest_frame_jpeg
    if latest_frame_jpeg is None:
        # Generate a placeholder dark canvas with text
        placeholder = np.zeros((240, 320, 3), dtype=np.uint8) + 25
        cv2.putText(
            placeholder,
            "Waiting for ESP32 Frame...",
            (35, 125),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (160, 160, 160),
            1,
            cv2.LINE_AA,
        )
        _, buf = cv2.imencode(".jpg", placeholder)
        frame_bytes = buf.tobytes()
    else:
        frame_bytes = latest_frame_jpeg

    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@router.post("/test", response_model=BiometricScanResponse)
async def test_palm_recognition(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Manual upload testing endpoint."""
    content = await file.read()
    nparr = np.frombuffer(content, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file uploaded.")

    set_latest_preview_frame(image)
    save_debug_image(image, prefix="test_manual")

    is_valid_quality, quality_reason = validate_image_quality(image)
    if not is_valid_quality:
        return BiometricScanResponse(status=BiometricStatus.LOW_QUALITY, message=f"Quality check failed: {quality_reason}")

    features = palm_extractor.extract(image)
    if features is None:
        return BiometricScanResponse(status=BiometricStatus.LOW_QUALITY, message="Palm not detected in test image.")

    matched_user, confidence, match_status = palm_matcher.match(features, db)

    if match_status == "MATCH_FOUND" and matched_user:
        _record_scan_event(
            db,
            status=BiometricStatus.MATCH_FOUND,
            user_id=matched_user.user_id,
            user_name=matched_user.name,
            confidence=confidence,
            message="Manual test palm matched."
        )
        return BiometricScanResponse(
            status=BiometricStatus.MATCH_FOUND,
            user_id=matched_user.user_id,
            name=matched_user.name,
            confidence=confidence,
            message="Palm matched successfully."
        )

    _record_scan_event(db, status=BiometricStatus.NO_MATCH, confidence=confidence, message="No match in test.")
    return BiometricScanResponse(
        status=BiometricStatus.NO_MATCH,
        confidence=confidence,
        message="No match found."
    )


@router.get("/latest", response_model=BiometricLatestResponse)
def get_latest_scan_event(db: Session = Depends(get_db)):
    """Frontend polling endpoint: Returns the most recent biometric scan event."""
    latest = db.query(BiometricScanEvent).order_by(BiometricScanEvent.created_at.desc()).first()
    if not latest:
        return BiometricLatestResponse(
            status=BiometricStatus.NO_MATCH,
            message="No scan events recorded yet."
        )

    return BiometricLatestResponse(
        event_id=latest.event_id,
        status=BiometricStatus(latest.status),
        user_id=latest.user_id,
        name=latest.user_name,
        confidence=latest.confidence,
        message=latest.message,
        timestamp=latest.created_at
    )


def _record_scan_event(
    db: Session,
    status: BiometricStatus,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    confidence: Optional[float] = None,
    message: Optional[str] = None
):
    """Records scan event in database."""
    try:
        event = BiometricScanEvent(
            event_id=generate_event_id(),
            status=status.value,
            user_id=user_id,
            user_name=user_name,
            confidence=confidence,
            message=message
        )
        db.add(event)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record scan event: {e}")
        db.rollback()
