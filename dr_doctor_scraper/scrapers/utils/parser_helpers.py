from __future__ import annotations

import re
from typing import Any, Callable, Optional


def clean_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def extract_number(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    numbers = re.findall(r"[0-9]+(?:\.[0-9]+)?", text.replace(",", ""))
    return float(numbers[0]) if numbers else None


def normalize_fee(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    numbers = re.findall(r"[0-9]+", text.replace(",", ""))
    return int(numbers[0]) if numbers else None


def safe_get(source: Any, getter: Callable[[Any], Any], default: Any = None) -> Any:
    """Safely call a getter on a source object, returning default on any error."""

    try:
        return getter(source)
    except Exception:  # noqa: BLE001
        return default
