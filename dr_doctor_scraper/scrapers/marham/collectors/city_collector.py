"""City collector for extracting all cities from Marham hospitals page."""

from __future__ import annotations

import requests
from typing import List, Dict
from bs4 import BeautifulSoup

from scrapers.logger import logger

BASE_URL = "https://www.marham.pk"
HOSPITALS_PAGE = f"{BASE_URL}/hospitals"


class CityCollector:
    """Collects all cities from the Marham hospitals listing page.
    
    Uses simple HTTP requests (no browser needed) to extract city names and URLs.
    """
    
    @staticmethod
    def collect_cities() -> List[Dict[str, str]]:
        """Extract all cities from the hospitals page.
        
        Parses both "Top Cities" and "Other Cities" sections.
        
        Returns:
            List of dictionaries with keys: name, url
        """
        logger.info("Collecting cities from {}", HOSPITALS_PAGE)
        
        try:
            response = requests.get(HOSPITALS_PAGE, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch hospitals page: {}", exc)
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        cities = []
        
        # Extract cities from "Top Cities" section
        # Look for links in the top cities section
        top_cities_section = soup.find("h2", string=lambda text: text and "Top Cities" in text)
        if top_cities_section:
            # Find the parent container and look for city links
            parent = top_cities_section.find_parent()
            if parent:
                # Look for links that match the pattern /hospitals/{city}
                city_links = parent.find_all("a", href=True)
                for link in city_links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    if "/hospitals/" in href and text:
                        city_name = text.strip()
                        # Normalize URL
                        if href.startswith("/"):
                            url = f"{BASE_URL}{href}"
                        elif href.startswith("http"):
                            url = href
                        else:
                            url = f"{BASE_URL}/hospitals/{href}"
                        
                        cities.append({"name": city_name, "url": url})
                        logger.debug("Found top city: {} -> {}", city_name, url)
        
        # Extract cities from "Other Cities" section
        other_cities_section = soup.find("h2", string=lambda text: text and "Other Cities" in text)
        if other_cities_section:
            # Find the parent container (usually a <ul> or <div>)
            parent = other_cities_section.find_next_sibling()
            if not parent:
                # Sometimes it's in a parent div
                parent = other_cities_section.find_parent()
            
            if parent:
                # Look for all links in this section
                city_links = parent.find_all("a", href=True)
                for link in city_links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True)
                    
                    # Filter for hospital city links
                    if "/hospitals/" in href and text:
                        # Extract city name from text (e.g., "Hospitals in Lahore" -> "Lahore")
                        city_name = text.replace("Hospitals in", "").strip()
                        if not city_name:
                            city_name = text.strip()
                        
                        # Normalize URL
                        if href.startswith("/"):
                            url = f"{BASE_URL}{href}"
                        elif href.startswith("http"):
                            url = href
                        else:
                            # Extract city slug from href
                            if "/hospitals/" in href:
                                parts = href.split("/hospitals/")
                                if len(parts) > 1:
                                    city_slug = parts[1].split("/")[0].split("?")[0]
                                    url = f"{BASE_URL}/hospitals/{city_slug}"
                                else:
                                    url = f"{BASE_URL}/hospitals/{href}"
                            else:
                                url = f"{BASE_URL}/hospitals/{href}"
                        
                        # Avoid duplicates
                        if not any(c["name"].lower() == city_name.lower() for c in cities):
                            cities.append({"name": city_name, "url": url})
                            logger.debug("Found other city: {} -> {}", city_name, url)
        
        # Also try to extract from any list items that contain city links
        # This is a fallback for different page structures
        all_city_links = soup.find_all("a", href=lambda href: href and "/hospitals/" in href)
        for link in all_city_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            
            if text and "/hospitals/" in href:
                # Extract city name
                city_name = text.replace("Hospitals in", "").replace("Hospitals", "").strip()
                if not city_name or len(city_name) < 2:
                    continue
                
                # Normalize URL
                if href.startswith("/"):
                    url = f"{BASE_URL}{href}"
                elif href.startswith("http"):
                    url = href
                else:
                    url = f"{BASE_URL}/hospitals/{href}"
                
                # Avoid duplicates
                if not any(c["name"].lower() == city_name.lower() or c["url"] == url for c in cities):
                    cities.append({"name": city_name, "url": url})
                    logger.debug("Found city (fallback): {} -> {}", city_name, url)
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_cities = []
        for city in cities:
            if city["url"] not in seen_urls:
                seen_urls.add(city["url"])
                unique_cities.append(city)
        
        logger.info("Collected {} unique cities", len(unique_cities))
        return unique_cities

