"""
Model pricing calculator – Phase 4, Step 2.2.

Token prices are sourced from the Gemini pricing page (approximate rates).
All costs are in USD. Calculations use Decimal for financial accuracy.
"""
from __future__ import annotations

from decimal import Decimal

# ---------------------------------------------------------------------------
# Price table  (per 1 million tokens, USD)
# ---------------------------------------------------------------------------
# Gemini 2.5 Flash / 3.8 Flash: tiered pricing; we use the standard non-cached rate.
# Gemini Embedding 2: single rate, no input/output distinction.

_PRICING: dict[str, dict[str, Decimal]] = {
    # Gemini 3.8 Flash
    "gemini-3.8-flash": {
        "input":  Decimal("0.075"),
        "output": Decimal("0.30"),
    },
    # Gemini 2.5 Flash (same tier)
    "gemini-2.5-flash": {
        "input":  Decimal("0.075"),
        "output": Decimal("0.30"),
    },
    # Gemini 2.5 Flash Preview
    "gemini-2.5-flash-preview-04-17": {
        "input":  Decimal("0.075"),
        "output": Decimal("0.30"),
    },
    # Gemini Embedding 2 (no in/out split – treated as input-only)
    "gemini-embedding-2": {
        "input":  Decimal("0.02"),
        "output": Decimal("0"),
    },
    "text-embedding-004": {
        "input":  Decimal("0.02"),
        "output": Decimal("0"),
    },
}

_MILLION = Decimal("1_000_000")
_ZERO = Decimal("0")


def calculate_cost(
    *,
    model: str,
    tokens_in: int,
    tokens_out: int = 0,
) -> Decimal:
    """Return the USD cost for a single Gemini API call.

    Unknown models fall back to zero cost so telemetry is never blocked.

    Args:
        model:      The model identifier string (e.g. ``"gemini-3.8-flash"``).
        tokens_in:  Number of input / prompt tokens consumed.
        tokens_out: Number of output / completion tokens generated.

    Returns:
        Cost in USD as a ``Decimal`` rounded to 10 decimal places.
    """
    # Strip provider prefixes like "models/gemini-3.8-flash"
    key = model.split("/")[-1].lower()

    # Try exact match first, then prefix match for versioned model IDs.
    rates = _PRICING.get(key)
    if rates is None:
        for prefix, r in _PRICING.items():
            if key.startswith(prefix):
                rates = r
                break

    if rates is None:
        return _ZERO

    input_cost  = Decimal(tokens_in)  / _MILLION * rates["input"]
    output_cost = Decimal(tokens_out) / _MILLION * rates["output"]
    return (input_cost + output_cost).quantize(Decimal("0.0000000001"))
