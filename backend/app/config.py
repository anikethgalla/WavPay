"""Application configuration settings using Pydantic Settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment or .env file."""

    # Server Settings
    BACKEND_URL: str = "http://localhost:8000"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Device & Security
    DEVICE_API_KEY: str = "esp32_palm_auth_secret_key_2026"
    
    # Database
    DATABASE_URL: str = "sqlite:///./data/palm_biometric.db"

    # Biometrics
    MATCH_THRESHOLD: float = 0.72
    MAX_IMAGE_SIZE_MB: int = 2
    PALM_ROI_SIZE: int = 128
    
    # Razorpay (Test Mode Credentials)
    RAZORPAY_KEY_ID: str = "rzp_test_mock_key_id"
    RAZORPAY_KEY_SECRET: str = "rzp_test_mock_secret_key"

    # Debug & Storage
    DEBUG: bool = True
    STORE_DEBUG_IMAGES: bool = True

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure required runtime directories exist
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ENROLLED_DIR = DATA_DIR / "enrolled_palms"
DEBUG_DIR = DATA_DIR / "debug_frames"

DATA_DIR.mkdir(parents=True, exist_ok=True)
ENROLLED_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
