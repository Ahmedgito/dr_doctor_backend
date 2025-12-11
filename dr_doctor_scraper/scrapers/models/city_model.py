"""City model for tracking cities to scrape."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CityModel(BaseModel):
    """Model for city entries in the cities collection.
    
    Tracks which cities have been scraped and their URLs.
    """
    name: str
    url: str  # Format: https://www.marham.pk/hospitals/{city}
    platform: str = "marham"
    scrape_status: str = "pending"  # "pending" or "scraped"
    scraped_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

