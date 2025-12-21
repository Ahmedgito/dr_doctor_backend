"""Utility functions for web crawler."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from typing import List, Set


def normalize_url(url: str, base_url: str) -> str:
    """Normalize a URL by resolving relative URLs and removing fragments.
    
    Args:
        url: URL to normalize (can be relative or absolute)
        base_url: Base URL for resolving relative URLs
        
    Returns:
        Normalized absolute URL without fragment
    """
    if not url:
        return ""
    
    # Remove whitespace
    url = url.strip()
    
    # Skip non-HTTP(S) URLs
    if url.startswith(("mailto:", "tel:", "javascript:", "data:")):
        return ""
    
    # Resolve relative URLs
    absolute_url = urljoin(base_url, url)
    
    # Parse URL
    parsed = urlparse(absolute_url)
    
    # Remove fragment
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        parsed.query,
        ""  # Remove fragment
    ))
    
    # Remove trailing slash for consistency (except for root)
    if normalized.endswith("/") and len(parsed.path) > 1:
        normalized = normalized[:-1]
    
    return normalized


def extract_domain(url: str) -> str:
    """Extract domain from URL.
    
    Args:
        url: URL to extract domain from
        
    Returns:
        Domain name (e.g., "marham.pk")
    """
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Remove port if present
    if ":" in domain:
        domain = domain.split(":")[0]
    
    # Remove www. prefix for consistency
    if domain.startswith("www."):
        domain = domain[4:]
    
    return domain


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs belong to the same domain.
    
    Args:
        url1: First URL
        url2: Second URL
        
    Returns:
        True if URLs belong to same domain
    """
    domain1 = extract_domain(url1)
    domain2 = extract_domain(url2)
    return domain1 == domain2


def should_crawl_url(url: str, config) -> bool:
    """Determine if a URL should be crawled based on configuration.
    
    Args:
        url: URL to check
        config: CrawlerConfig instance
        
    Returns:
        True if URL should be crawled
    """
    if not url:
        return False
    
    # Must be HTTP or HTTPS
    if not url.startswith(("http://", "https://")):
        return False
    
    # Check if domain is allowed
    domain = extract_domain(url)
    if config.allowed_domains:
        if not any(extract_domain(allowed) == domain for allowed in config.allowed_domains):
            return False
    
    # Filter out file downloads
    file_extensions = [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".rar", ".tar", ".gz", ".7z",
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
        ".mp4", ".avi", ".mov", ".wmv", ".flv",
        ".mp3", ".wav", ".ogg", ".flac",
        ".exe", ".dmg", ".deb", ".rpm"
    ]
    
    url_lower = url.lower()
    if any(url_lower.endswith(ext) for ext in file_extensions):
        return False
    
    # Filter out common non-page URLs
    excluded_patterns = [
        r"/feed",
        r"/rss",
        r"/atom",
        r"/sitemap",
        r"/robots\.txt",
        r"/api/",
        r"/ajax/",
        r"/json/",
    ]
    
    for pattern in excluded_patterns:
        if re.search(pattern, url_lower):
            return False
    
    return True


def extract_links_from_html(html: str, base_url: str) -> List[str]:
    """Extract all links from HTML content.
    
    Args:
        html: HTML content
        base_url: Base URL for resolving relative URLs
        
    Returns:
        List of normalized absolute URLs
    """
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, "html.parser")
    links: Set[str] = set()
    
    # Find all <a> tags with href
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "").strip()
        if href:
            normalized = normalize_url(href, base_url)
            if normalized:
                links.add(normalized)
    
    return list(links)


def clean_url_query(url: str, keep_params: Optional[List[str]] = None) -> str:
    """Clean URL query parameters, optionally keeping specific ones.
    
    Args:
        url: URL to clean
        keep_params: List of parameter names to keep (None = remove all)
        
    Returns:
        URL with cleaned query string
    """
    parsed = urlparse(url)
    if not parsed.query:
        return url
    
    if keep_params is None:
        # Remove all query parameters
        cleaned = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            "",
            parsed.fragment
        ))
    else:
        # Keep only specified parameters
        params = parse_qs(parsed.query)
        filtered_params = {k: v for k, v in params.items() if k in keep_params}
        query = urlencode(filtered_params, doseq=True)
        cleaned = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query,
            parsed.fragment
        ))
    
    return cleaned


