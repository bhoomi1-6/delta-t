"""Load local backend environment settings."""

from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]


def load_backend_environment() -> None:
    """Load backend/.env without overriding variables already in the process."""
    load_dotenv(BACKEND_DIR / ".env")
