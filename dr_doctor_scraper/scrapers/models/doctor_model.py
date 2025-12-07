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
    # List of hospital affiliations with name+url+fee+timings
    hospitals: Optional[List[dict]] = None
    # Private practice information (for video consultations, home visits, etc.)
    private_practice: Optional[dict] = None  # {name: str, url: str, fee: int, timings: dict}
    address: Optional[str]
    rating: Optional[float]
    pmdc_verified: Optional[bool] = False
    qualifications: Optional[List[dict]] = None
    experience_years: Optional[int] = None
    work_history: Optional[List[dict]] = None
    services: Optional[List[str]] = None
    diseases: Optional[List[str]] = None
    symptoms: Optional[List[str]] = None
    experience: Optional[str] = None
    professional_statement: Optional[str] = None
    patients_treated: Optional[int] = None
    reviews_count: Optional[int] = None
    patient_satisfaction_score: Optional[float] = None
    phone: Optional[str] = None
    consultation_types: Optional[List[str]] = None
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
