"""Sitemap.xml parser for discovering URLs."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
import requests

from scrapers.logger import logger
from scrapers.crawler.utils import extract_domain, normalize_url


class SitemapParser:
    """Parser for sitemap.xml and sitemap_index.xml files."""
    
    SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    
    def __init__(self, base_url: str):
        """Initialize sitemap parser.
        
        Args:
            base_url: Base URL of the website
        """
        self.base_url = base_url
        self.domain = extract_domain(base_url)
    
    def discover_sitemaps(self) -> List[str]:
        """Discover sitemap URLs from common locations.
        
        Returns:
            List of sitemap URLs
        """
        sitemaps = []
        
        # Standard locations
        standard_paths = [
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap-index.xml",
        ]
        
        for path in standard_paths:
            url = urljoin(self.base_url, path)
            try:
                response = requests.head(url, timeout=10, allow_redirects=True)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "").lower()
                    if "xml" in content_type:
                        sitemaps.append(url)
                        logger.info("Found sitemap at: {}", url)
            except Exception as exc:
                logger.debug("Could not fetch {}: {}", url, exc)
        
        # Check robots.txt
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            response = requests.get(robots_url, timeout=10)
            if response.status_code == 200:
                for line in response.text.split("\n"):
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        sitemaps.append(sitemap_url)
                        logger.info("Found sitemap in robots.txt: {}", sitemap_url)
        except Exception as exc:
            logger.debug("Could not fetch robots.txt: {}", exc)
        
        return list(set(sitemaps))  # Remove duplicates
    
    def parse_sitemap(self, sitemap_url: str) -> List[Dict]:
        """Parse a sitemap.xml file and extract URLs.
        
        Args:
            sitemap_url: URL of the sitemap file
            
        Returns:
            List of dictionaries with URL information:
            - url: str
            - lastmod: Optional[str]
            - changefreq: Optional[str]
            - priority: Optional[float]
        """
        try:
            response = requests.get(sitemap_url, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            # Check if it's a sitemap index
            if root.tag.endswith("sitemapindex"):
                return self._parse_sitemap_index(root, sitemap_url)
            else:
                return self._parse_sitemap(root)
        
        except Exception as exc:
            logger.warning("Failed to parse sitemap {}: {}", sitemap_url, exc)
            return []
    
    def _parse_sitemap_index(self, root: ET.Element, base_url: str) -> List[Dict]:
        """Parse a sitemap index file.
        
        Args:
            root: XML root element
            base_url: Base URL for resolving relative URLs
            
        Returns:
            List of sitemap URLs to parse
        """
        sitemaps = []
        
        for sitemap_elem in root.findall(".//sm:sitemap", self.SITEMAP_NAMESPACE):
            loc_elem = sitemap_elem.find("sm:loc", self.SITEMAP_NAMESPACE)
            if loc_elem is not None and loc_elem.text:
                sitemap_url = normalize_url(loc_elem.text, base_url)
                sitemaps.append({"url": sitemap_url, "type": "sitemap"})
        
        # If namespace not found, try without namespace
        if not sitemaps:
            for sitemap_elem in root.findall(".//sitemap"):
                loc_elem = sitemap_elem.find("loc")
                if loc_elem is not None and loc_elem.text:
                    sitemap_url = normalize_url(loc_elem.text, base_url)
                    sitemaps.append({"url": sitemap_url, "type": "sitemap"})
        
        return sitemaps
    
    def _parse_sitemap(self, root: ET.Element) -> List[Dict]:
        """Parse a regular sitemap file.
        
        Args:
            root: XML root element
            
        Returns:
            List of URL dictionaries
        """
        urls = []
        
        for url_elem in root.findall(".//sm:url", self.SITEMAP_NAMESPACE):
            loc_elem = url_elem.find("sm:loc", self.SITEMAP_NAMESPACE)
            if loc_elem is not None and loc_elem.text:
                url_data = {"url": normalize_url(loc_elem.text, self.base_url)}
                
                # Extract optional metadata
                lastmod_elem = url_elem.find("sm:lastmod", self.SITEMAP_NAMESPACE)
                if lastmod_elem is not None and lastmod_elem.text:
                    url_data["lastmod"] = lastmod_elem.text
                
                changefreq_elem = url_elem.find("sm:changefreq", self.SITEMAP_NAMESPACE)
                if changefreq_elem is not None and changefreq_elem.text:
                    url_data["changefreq"] = changefreq_elem.text
                
                priority_elem = url_elem.find("sm:priority", self.SITEMAP_NAMESPACE)
                if priority_elem is not None and priority_elem.text:
                    try:
                        url_data["priority"] = float(priority_elem.text)
                    except ValueError:
                        pass
                
                urls.append(url_data)
        
        # If namespace not found, try without namespace
        if not urls:
            for url_elem in root.findall(".//url"):
                loc_elem = url_elem.find("loc")
                if loc_elem is not None and loc_elem.text:
                    url_data = {"url": normalize_url(loc_elem.text, self.base_url)}
                    
                    lastmod_elem = url_elem.find("lastmod")
                    if lastmod_elem is not None and lastmod_elem.text:
                        url_data["lastmod"] = lastmod_elem.text
                    
                    changefreq_elem = url_elem.find("changefreq")
                    if changefreq_elem is not None and changefreq_elem.text:
                        url_data["changefreq"] = changefreq_elem.text
                    
                    priority_elem = url_elem.find("priority")
                    if priority_elem is not None and priority_elem.text:
                        try:
                            url_data["priority"] = float(priority_elem.text)
                        except ValueError:
                            pass
                    
                    urls.append(url_data)
        
        return urls
    
    def get_all_urls(self) -> List[str]:
        """Get all URLs from all discovered sitemaps.
        
        Returns:
            List of URLs
        """
        all_urls = []
        sitemap_urls = self.discover_sitemaps()
        
        for sitemap_url in sitemap_urls:
            logger.info("Parsing sitemap: {}", sitemap_url)
            parsed = self.parse_sitemap(sitemap_url)
            
            # If it's a sitemap index, parse each referenced sitemap
            for item in parsed:
                if item.get("type") == "sitemap":
                    # It's a sitemap index entry, parse the referenced sitemap
                    nested_urls = self.parse_sitemap(item["url"])
                    all_urls.extend([u["url"] for u in nested_urls if "url" in u])
                elif "url" in item:
                    # It's a regular URL entry
                    all_urls.append(item["url"])
        
        # Filter to same domain only
        all_urls = [url for url in all_urls if extract_domain(url) == self.domain]
        
        logger.info("Found {} URLs from sitemaps", len(all_urls))
        return list(set(all_urls))  # Remove duplicates


