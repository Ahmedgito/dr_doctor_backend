from __future__ import annotations

import re
from typing import Any, Callable, Optional


def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean and normalize text string by removing extra whitespace.
    
    Args:
        text: Text string to clean (can be None)
        
    Returns:
        Cleaned text with normalized whitespace, or None if input was None/empty
    """
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned or None


def extract_number(text: Optional[str]) -> Optional[float]:
    """Extract the first numeric value from text string.
    
    Handles integers and decimals, removes commas from numbers.
    
    Args:
        text: Text string containing a number (can be None)
        
    Returns:
        First number found as float, or None if no number found
    """
    if text is None:
        return None
    numbers = re.findall(r"[0-9]+(?:\.[0-9]+)?", text.replace(",", ""))
    return float(numbers[0]) if numbers else None


def normalize_fee(text: Optional[str]) -> Optional[int]:
    """Extract and normalize fee amount from text to integer.
    
    Removes commas and extracts first integer value.
    Used for parsing fee strings like "PKR 1,500" -> 1500.
    
    Args:
        text: Fee text string (can be None)
        
    Returns:
        Fee as integer, or None if no number found
    """
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
