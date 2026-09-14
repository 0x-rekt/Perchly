import sqlite3
from pathlib import Path

from app.core.config import DATA_DIRECTORY


class IdempotencyStore:
    """Durable protection against duplicate webhook deliveries and review comments."""

    def __init__(self, database_path: Path | None = None) -> None:
        self._database_path = database_path or DATA_DIRECTORY / "perchly.sqlite3"
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS webhook_deliveries (delivery_id TEXT PRIMARY KEY, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS review_runs (repository TEXT NOT NULL, pr_number INTEGER NOT NULL, head_sha TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (repository, pr_number, head_sha))"
            )

    def claim(self, *, delivery_id: str, repository: str, pr_number: int, head_sha: str) -> bool:
        """Claim a delivery and commit review atomically; false means it is already known."""
        with self._connect() as connection:
            try:
                connection.execute("INSERT INTO webhook_deliveries (delivery_id) VALUES (?)", (delivery_id,))
                connection.execute(
                    "INSERT INTO review_runs (repository, pr_number, head_sha) VALUES (?, ?, ?)",
                    (repository, pr_number, head_sha),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def release_review(self, *, repository: str, pr_number: int, head_sha: str) -> None:
        """Permit a later, distinct delivery to retry a failed review for this commit."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM review_runs WHERE repository = ? AND pr_number = ? AND head_sha = ?",
                (repository, pr_number, head_sha),
            )
