"""Asset discovery for crawled pages."""

from __future__ import annotations

import re
from typing import List, Dict
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scrapers.logger import logger
from scrapers.crawler.utils import extract_domain, normalize_url


class AssetDiscoverer:
    """Discovers and catalogs assets (images, CSS, JS, etc.) from pages."""
    
    def __init__(self, base_url: str):
        """Initialize asset discoverer.
        
        Args:
            base_url: Base URL of the page
        """
        self.base_url = base_url
        self.domain = extract_domain(base_url)
    
    def discover_assets(self, html: str, page_url: str) -> List[Dict]:
        """Discover all assets from HTML content.
        
        Args:
            html: HTML content
            page_url: URL of the page
            
        Returns:
            List of asset dictionaries:
            - url: str
            - asset_type: str (image, stylesheet, script, font, video, document)
            - alt_text: Optional[str] (for images)
            - dimensions: Optional[Dict] (for images)
        """
        soup = BeautifulSoup(html, "html.parser")
        assets = []
        
        # Discover images
        assets.extend(self._discover_images(soup, page_url))
        
        # Discover stylesheets
        assets.extend(self._discover_stylesheets(soup, page_url))
        
        # Discover scripts
        assets.extend(self._discover_scripts(soup, page_url))
        
        # Discover fonts
        assets.extend(self._discover_fonts(soup, page_url))
        
        # Discover videos
        assets.extend(self._discover_videos(soup, page_url))
        
        return assets
    
    def _discover_images(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Discover image assets.
        
        Args:
            soup: BeautifulSoup object
            page_url: URL of the page
            
        Returns:
            List of image asset dictionaries
        """
        images = []
        
        # <img> tags
        for img in soup.find_all("img", src=True):
            src = img.get("src", "").strip()
            if src:
                asset_url = normalize_url(src, page_url)
                if asset_url:
                    asset = {
                        "url": asset_url,
                        "asset_type": "image",
                        "parent_url": page_url,
                        "domain": self.domain,
                    }
                    
                    # Extract alt text
                    alt = img.get("alt", "")
                    if alt:
                        asset["alt_text"] = alt
                    
                    # Extract dimensions
                    width = img.get("width")
                    height = img.get("height")
                    if width and height:
                        try:
                            asset["dimensions"] = {
                                "width": int(width),
                                "height": int(height),
                            }
                        except ValueError:
                            pass
                    
                    images.append(asset)
        
        # CSS background images (basic extraction)
        # This is a simplified version - full CSS parsing would be more complex
        style_tags = soup.find_all("style")
        for style in style_tags:
            style_text = style.string or ""
            # Look for url() patterns
            url_pattern = r"url\(['\"]?([^'\")]+)['\"]?\)"
            matches = re.findall(url_pattern, style_text)
            for match in matches:
                if any(ext in match.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"]):
                    asset_url = normalize_url(match, page_url)
                    if asset_url:
                        images.append({
                            "url": asset_url,
                            "asset_type": "image",
                            "parent_url": page_url,
                            "domain": self.domain,
                        })
        
        return images
    
    def _discover_stylesheets(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Discover stylesheet assets.
        
        Args:
            soup: BeautifulSoup object
            page_url: URL of the page
            
        Returns:
            List of stylesheet asset dictionaries
        """
        stylesheets = []
        
        # <link rel="stylesheet"> tags
        for link in soup.find_all("link", rel="stylesheet", href=True):
            href = link.get("href", "").strip()
            if href:
                asset_url = normalize_url(href, page_url)
                if asset_url:
                    stylesheets.append({
                        "url": asset_url,
                        "asset_type": "stylesheet",
                        "parent_url": page_url,
                        "domain": self.domain,
                    })
        
        return stylesheets
    
    def _discover_scripts(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Discover JavaScript assets.
        
        Args:
            soup: BeautifulSoup object
            page_url: URL of the page
            
        Returns:
            List of script asset dictionaries
        """
        scripts = []
        
        # <script src=""> tags (exclude inline scripts)
        for script in soup.find_all("script", src=True):
            src = script.get("src", "").strip()
            if src:
                asset_url = normalize_url(src, page_url)
                if asset_url:
                    scripts.append({
                        "url": asset_url,
                        "asset_type": "script",
                        "parent_url": page_url,
                        "domain": self.domain,
                    })
        
        return scripts
    
    def _discover_fonts(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Discover font assets.
        
        Args:
            soup: BeautifulSoup object
            page_url: URL of the page
            
        Returns:
            List of font asset dictionaries
        """
        fonts = []
        
        # <link rel="preload" as="font"> or font files in CSS
        for link in soup.find_all("link", href=True):
            href = link.get("href", "").strip()
            rel = link.get("rel", [])
            if isinstance(rel, list):
                rel = " ".join(rel)
            rel = rel.lower()
            
            if "font" in rel or any(ext in href.lower() for ext in [".woff", ".woff2", ".ttf", ".otf", ".eot"]):
                asset_url = normalize_url(href, page_url)
                if asset_url:
                    fonts.append({
                        "url": asset_url,
                        "asset_type": "font",
                        "parent_url": page_url,
                        "domain": self.domain,
                    })
        
        # Check @font-face in style tags
        style_tags = soup.find_all("style")
        for style in style_tags:
            style_text = style.string or ""
            url_pattern = r"url\(['\"]?([^'\")]+)['\"]?\)"
            matches = re.findall(url_pattern, style_text)
            for match in matches:
                if any(ext in match.lower() for ext in [".woff", ".woff2", ".ttf", ".otf", ".eot"]):
                    asset_url = normalize_url(match, page_url)
                    if asset_url:
                        fonts.append({
                            "url": asset_url,
                            "asset_type": "font",
                            "parent_url": page_url,
                            "domain": self.domain,
                        })
        
        return fonts
    
    def _discover_videos(self, soup: BeautifulSoup, page_url: str) -> List[Dict]:
        """Discover video assets.
        
        Args:
            soup: BeautifulSoup object
            page_url: URL of the page
            
        Returns:
            List of video asset dictionaries
        """
        videos = []
        
        # <video> tags
        for video in soup.find_all("video", src=True):
            src = video.get("src", "").strip()
            if src:
                asset_url = normalize_url(src, page_url)
                if asset_url:
                    videos.append({
                        "url": asset_url,
                        "asset_type": "video",
                        "parent_url": page_url,
                        "domain": self.domain,
                    })
        
        # <source> tags within <video>
        for source in soup.find_all("source", src=True):
            src = source.get("src", "").strip()
            if src:
                asset_url = normalize_url(src, page_url)
                if asset_url:
                    videos.append({
                        "url": asset_url,
                        "asset_type": "video",
                        "parent_url": page_url,
                        "domain": self.domain,
                    })
        
        return videos


