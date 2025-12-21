"""Pydantic models for crawled pages and site maps."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CrawledPage(BaseModel):
    """Model for a crawled page."""
    
    url: str
    title: Optional[str] = None
    parent_url: Optional[str] = None
    depth: int = 0
    content_type: Optional[str] = None  # e.g., "listing", "detail", "form"
    data_types: List[str] = Field(default_factory=list)  # e.g., ["doctor_list", "hospital_info"]
    keywords_found: List[str] = Field(default_factory=list)
    keyword_scores: Dict[str, float] = Field(default_factory=dict)
    html_structure: Dict = Field(default_factory=dict)  # forms, tables, lists detected
    links_found: List[str] = Field(default_factory=list)  # all links on page
    assets_found: List[Dict] = Field(default_factory=list)  # images, CSS, JS files
    status_code: Optional[int] = None
    crawled_at: datetime = Field(default_factory=datetime.utcnow)
    crawl_status: str = "pending"  # "pending", "crawled", "failed"
    error_message: Optional[str] = None
    requires_js: Optional[bool] = None  # Whether page requires JavaScript
    domain: Optional[str] = None
    
    class Config:
        orm_mode = True


class SiteMap(BaseModel):
    """Model for site map structure."""
    
    domain: str
    root_url: str
    total_pages: int = 0
    max_depth: int = 0
    pages_by_depth: Dict[int, int] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True


class CrawledAsset(BaseModel):
    """Model for discovered assets (images, CSS, JS, etc.)."""
    
    url: str
    asset_type: str  # "image", "stylesheet", "script", "font", "video", "document"
    parent_url: str  # URL of page that contains this asset
    domain: str
    alt_text: Optional[str] = None  # For images
    dimensions: Optional[Dict[str, int]] = None  # For images: {"width": int, "height": int}
    size: Optional[int] = None  # Size in bytes if available
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        orm_mode = True


