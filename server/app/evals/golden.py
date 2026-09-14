import json
from pathlib import Path

GOLDEN_FIXTURE_DIRECTORY = Path(__file__).with_name("fixtures")


def load_golden_cases() -> list[dict[str, object]]:
    """Load the small, versioned Phase 0 golden PR dataset."""
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(GOLDEN_FIXTURE_DIRECTORY.glob("*.json"))]
