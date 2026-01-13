import os
from pathlib import Path
from typing import Optional


def load_env_file(env_path: Path) -> None:
    """Load environment variables from .env file"""
    if not env_path.exists():
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ.setdefault(key, value)


# Load .env file from project root
PROJECT_ROOT = Path(__file__).parent.parent
load_env_file(PROJECT_ROOT / ".env")


class Config:
    """Application configuration"""

    # API Settings
    API_URL = "https://data.emergency.vic.gov.au/Show?pageId=getIncidentJSON"
    API_TIMEOUT = 30

    # Geocoding
    AZURE_MAPS_API_KEY: Optional[str] = os.getenv("AZURE_MAPS_API_KEY") or None
    GOOGLE_MAPS_API_KEY: Optional[str] = os.getenv("GOOGLE_MAPS_API_KEY") or None

    # Polling
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "3600"))

    # Output
    OUTPUT_FORMAT: str = os.getenv("OUTPUT_FORMAT", "table")

    # Notifications
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL") or None

    # Email
    SMTP_HOST: Optional[str] = os.getenv("SMTP_HOST") or None
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: Optional[str] = os.getenv("SMTP_USER") or None
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD") or None
    ALERT_EMAIL: Optional[str] = os.getenv("ALERT_EMAIL") or None

    # State persistence
    DATA_DIR = PROJECT_ROOT / "data"
    STATE_FILE = DATA_DIR / "state.json"

    @classmethod
    def ensure_data_dir(cls) -> None:
        cls.DATA_DIR.mkdir(exist_ok=True)
