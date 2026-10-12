"""FastAPI Main Application Entrypoint for Palm Biometric Payment System."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import biometric, payments, users
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Device, User
from app.utils.security import hash_api_key

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("palm_payment_system")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifespan events."""
    logger.info("Initializing database tables...")
    Base.metadata.create_all(bind=engine)

    # Seed master ESP32-CAM device authorization if empty
    db = SessionLocal()
    try:
        existing_device = db.query(Device).filter(Device.device_id == "ESP32_CAM_01").first()
        if not existing_device:
            dev = Device(
                device_id="ESP32_CAM_01",
                api_key_hash=hash_api_key(settings.DEVICE_API_KEY),
                active=True
            )
            db.add(dev)
            db.commit()
            logger.info("Seeded default ESP32_CAM_01 device authorization.")
    except Exception as e:
        logger.error(f"Error initializing default device: {e}")
    finally:
        db.close()

    yield
    logger.info("Shutting down Palm Biometric Payment System.")


app = FastAPI(
    title="Palm Biometric Payment Gateway",
    description="Real-time palm biometric identification, RGB565 frame decoding, and Razorpay payment integration for ESP32-CAM.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(biometric.router)
app.include_router(users.router)
app.include_router(payments.router)

# Mount frontend static directory
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


@app.get("/")
def root_endpoint():
    """Root endpoint: serves frontend index or API status."""
    index_file = frontend_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "system": "Palm Biometric Payment System",
        "status": "ONLINE",
        "docs": "/docs",
        "biometric_endpoint": "/api/biometric/scan"
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "HEALTHY",
        "database": "CONNECTED",
        "rgb565_decoder": "READY",
        "match_threshold": settings.MATCH_THRESHOLD
    }
