"""Page model for tracking pages that need to be scraped."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class PageModel(BaseModel):
    """Model for page entries in the pages collection.
    
    Tracks which pages have been scraped and which failed.
    """
    url: str  # Full page URL (e.g., https://www.marham.pk/hospitals/karachi?page=3)
    city_name: Optional[str] = None  # City name for reference
    city_url: Optional[str] = None  # City URL for reference
    page_number: Optional[int] = None  # Page number
    platform: str = "marham"
    scrape_status: str = "pending"  # "pending", "success", "failed", "retrying"
    error_message: Optional[str] = None  # Error message if failed
    retry_count: int = 0  # Number of retry attempts
    last_attempt: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scraped_at: Optional[datetime] = None


