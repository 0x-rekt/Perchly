import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH")
GITHUB_API_URL = "https://api.github.com"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def github_app_credentials() -> tuple[str, Path]:
    """Return GitHub App credentials or fail before a background job makes API calls."""
    if not GITHUB_APP_ID or not GITHUB_PRIVATE_KEY_PATH:
        raise RuntimeError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH must be configured")

    private_key_path = Path(GITHUB_PRIVATE_KEY_PATH)
    if not private_key_path.is_file():
        raise RuntimeError("GITHUB_PRIVATE_KEY_PATH does not point to a readable file")

    return GITHUB_APP_ID, private_key_path


def gemini_api_key() -> str:
    """Return the Gemini key without exposing it in logs or error messages."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY must be configured")
    return GEMINI_API_KEY
