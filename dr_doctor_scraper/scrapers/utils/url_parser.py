"""URL parsing utilities for Marham platform."""

from __future__ import annotations

import re
from typing import Optional, Dict

BASE_URL = "https://www.marham.pk"


def parse_hospital_url(url: str) -> Dict[str, Optional[str]]:
    """Parse hospital URL to extract city, name, and area.
    
    URL format: marham.pk/hospitals/(city)/(name)/(area)
    Example: https://www.marham.pk/hospitals/karachi/hashmanis-hospital-m-a-jinnah-road/jacob-lines
    
    Args:
        url: Hospital URL
        
    Returns:
        Dictionary with keys: city, name, area (all optional)
    """
    result = {"city": None, "name": None, "area": None}
    
    if not url:
        return result
    
    # Remove base URL and query parameters
    url = url.replace(BASE_URL, "").replace("https://www.marham.pk", "").replace("http://www.marham.pk", "")
    if "?" in url:
        url = url.split("?")[0]
    
    # Pattern: /hospitals/(city)/(name)/(area)
    pattern = r"/hospitals/([^/]+)/([^/]+)(?:/([^/]+))?"
    match = re.search(pattern, url)
    
    if match:
        result["city"] = match.group(1).replace("-", " ").title() if match.group(1) else None
        result["name"] = match.group(2).replace("-", " ").title() if match.group(2) else None
        result["area"] = match.group(3).replace("-", " ").title() if match.group(3) else None
    
    return result


def is_hospital_url(url: str) -> bool:
    """Check if URL is a hospital URL.
    
    Args:
        url: URL string to check
        
    Returns:
        True if URL contains '/hospitals/' path segment
    """
    if not url:
        return False
    return "/hospitals/" in url


def is_doctor_url(url: str) -> bool:
    """Check if URL is a doctor profile URL.
    
    Args:
        url: URL string to check
        
    Returns:
        True if URL contains '/doctors/' path segment
    """
    if not url:
        return False
    return "/doctors/" in url


def is_video_consultation_url(url: str) -> bool:
    """Check if URL is for video consultation (private practice).
    
    Args:
        url: URL string to check
        
    Returns:
        True if URL contains 'video' or 'consultation' keywords
    """
    if not url:
        return False
    # Video consultation URLs might have specific patterns
    # This needs to be updated based on actual URL patterns
    return "video" in url.lower() or "consultation" in url.lower()

