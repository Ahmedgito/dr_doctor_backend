from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class HospitalModel(BaseModel):
    name: str
    city: Optional[str]
    area: Optional[str]
    address: Optional[str]
    platform: str
    url: Optional[str]
    timing: Optional[str] = None
    specialties: Optional[List[str]] = None
    # Geolocation for hospital (if available)
    location: Optional[dict] = None  # {'lat': float, 'lng': float}
    # List of doctors affiliated with this hospital and their hospital-specific info
    doctors: Optional[List[dict]] = None
    about: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
