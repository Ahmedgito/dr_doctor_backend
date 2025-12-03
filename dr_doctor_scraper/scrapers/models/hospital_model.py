from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class HospitalModel(BaseModel):
    name: str
    city: Optional[str]
    area: Optional[str]
    address: Optional[str]
    platform: str
    url: Optional[str]
    scraped_at: datetime = datetime.utcnow()
