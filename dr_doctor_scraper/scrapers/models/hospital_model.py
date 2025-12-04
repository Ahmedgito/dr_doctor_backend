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
    founded_year: Optional[int] = None
    achievements: Optional[List[str]] = None
    clinical_departments: Optional[List[str]] = None
    specialized_procedures: Optional[dict] = None  # {category: [procedures]}
    facilities: Optional[List[str]] = None
    clinical_support_services: Optional[List[str]] = None
    fees_range: Optional[str] = None  # e.g., "2000-3500 PKR"
    contact_number: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
