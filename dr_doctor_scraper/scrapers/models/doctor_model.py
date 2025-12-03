from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class DoctorModel(BaseModel):
    name: str
    specialty: List[str]
    fees: Optional[int]
    city: Optional[ str ]
    area: Optional[str]
    hospital: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    experience: Optional[str]
    profile_url: str
    platform: str
    scraped_at: datetime = Field(default_factory=datetime.utcnow)

    @validator("name", "city", pre=True)
    def strip_strings(cls, v: Optional[str]) -> Optional[str]:  # noqa: D417, N805
        return v.strip() if isinstance(v, str) else v

    @validator("specialty", pre=True)
    def ensure_list(cls, v):  # noqa: D417, ANN001, N805
        if v is None:
            return []
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return parts
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return [str(v).strip()]

    @validator("fees", pre=True)
    def normalize_fees(cls, v):  # noqa: D417, ANN001, N805
        if v in (None, "", "-"):
            return None
        if isinstance(v, (int, float)):
            return int(v)
        # attempt to extract numbers like "PKR 1,500" or "1500 Rs"
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        return int(digits) if digits else None

    @validator("rating", pre=True)
    def normalize_rating(cls, v):  # noqa: D417, ANN001, N805
        if v in (None, "", "-"):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        text = str(v).strip().replace("/5", "")
        try:
            return float(text)
        except ValueError:
            return None

    class Config:
        orm_mode = True
