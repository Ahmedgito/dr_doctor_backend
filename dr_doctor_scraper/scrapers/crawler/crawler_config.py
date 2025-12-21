"""Configuration for web crawler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CrawlerConfig:
    """Configuration for web crawler."""
    
    start_urls: List[str]
    allowed_domains: Optional[List[str]] = None
    keywords: List[str] = field(default_factory=list)
    max_depth: Optional[int] = None
    respect_robots_txt: bool = True
    delay_between_requests: float = 0.5
    max_pages: Optional[int] = None
    num_threads: int = 1
    use_sitemap: bool = True
    detect_js: bool = True
    discover_assets: bool = True
    distributed: bool = False
    distributed_queue: str = "mongodb"  # "mongodb" or "redis"
    instance_id: Optional[str] = None
    
    # Browser settings
    headless: bool = True
    timeout_ms: int = 15000
    max_retries: int = 3
    wait_between_retries: float = 2.0
    disable_js: bool = False
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.start_urls:
            raise ValueError("start_urls cannot be empty")
        
        if self.num_threads < 1:
            raise ValueError("num_threads must be >= 1")
        
        if self.delay_between_requests < 0:
            raise ValueError("delay_between_requests must be >= 0")
        
        if self.max_depth is not None and self.max_depth < 0:
            raise ValueError("max_depth must be >= 0 or None")
        
        if self.max_pages is not None and self.max_pages < 1:
            raise ValueError("max_pages must be >= 1 or None")
        
        # Extract domains from start_urls if allowed_domains not provided
        if self.allowed_domains is None:
            # Import here to avoid circular import
            from urllib.parse import urlparse
            def extract_domain(url: str) -> str:
                parsed = urlparse(url)
                domain = parsed.netloc
                if ":" in domain:
                    domain = domain.split(":")[0]
                if domain.startswith("www."):
                    domain = domain[4:]
                return domain
            self.allowed_domains = [extract_domain(url) for url in self.start_urls]

