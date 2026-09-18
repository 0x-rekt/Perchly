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
DATABASE_URL = os.getenv("DATABASE_URL")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "5"))
AUTO_POST_THRESHOLD = float(os.getenv("PERCHLY_AUTO_POST_THRESHOLD", "0.90"))
SECURITY_AUTO_POST_THRESHOLD = float(
    os.getenv("PERCHLY_SECURITY_AUTO_POST_THRESHOLD", "0.95")
)
MAX_AUTO_POST_FINDINGS = int(os.getenv("PERCHLY_MAX_AUTO_POST_FINDINGS", "20"))
DATA_DIRECTORY = Path(os.getenv("PERCHLY_DATA_DIRECTORY", "data"))


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


def database_url() -> str:
    """Return the cloud PostgreSQL connection string without exposing it in logs."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be configured")
    return DATABASE_URL
