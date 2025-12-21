"""Content analysis for crawled pages."""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

from scrapers.logger import logger


class ContentAnalyzer:
    """Analyzes page content to detect types, patterns, and keywords."""
    
    def __init__(self, keywords: List[str] = None):
        """Initialize content analyzer.
        
        Args:
            keywords: List of keywords to search for
        """
        self.keywords = [kw.lower() for kw in (keywords or [])]
    
    def analyze(self, html: str, url: str) -> Dict:
        """Analyze page content and return analysis results.
        
        Args:
            html: HTML content of the page
            url: URL of the page
            
        Returns:
            Dictionary with analysis results:
            - content_type: str (listing, detail, form, search, etc.)
            - data_types: List[str]
            - keywords_found: List[str]
            - keyword_scores: Dict[str, float]
            - html_structure: Dict
        """
        soup = BeautifulSoup(html, "html.parser")
        
        result = {
            "content_type": self._detect_content_type(soup),
            "data_types": self._detect_data_types(soup),
            "keywords_found": [],
            "keyword_scores": {},
            "html_structure": self._analyze_html_structure(soup),
        }
        
        # Keyword matching
        if self.keywords:
            keywords_data = self._match_keywords(soup, html)
            result["keywords_found"] = keywords_data["found"]
            result["keyword_scores"] = keywords_data["scores"]
        
        return result
    
    def _detect_content_type(self, soup: BeautifulSoup) -> str:
        """Detect the type of content on the page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Content type string
        """
        # Check for forms
        forms = soup.find_all("form")
        if forms:
            # Check if it's a search form
            search_inputs = soup.find_all("input", {"type": ["search", "text"]}, 
                                         attrs={"name": re.compile(r"search|query|q", re.I)})
            if search_inputs:
                return "search"
            return "form"
        
        # Check for listing patterns (multiple similar cards/items)
        cards = soup.find_all(attrs={"class": re.compile(r"card|item|listing|result", re.I)})
        if len(cards) >= 3:
            return "listing"
        
        # Check for detail page patterns (single entity with detailed info)
        detail_indicators = soup.find_all(attrs={"class": re.compile(r"detail|profile|view|single", re.I)})
        if detail_indicators:
            return "detail"
        
        # Check for table-based listings
        tables = soup.find_all("table")
        if tables and len(tables[0].find_all("tr")) > 3:
            return "listing"
        
        # Default
        return "page"
    
    def _detect_data_types(self, soup: BeautifulSoup) -> List[str]:
        """Detect specific data types on the page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of detected data types
        """
        data_types = []
        text_content = soup.get_text().lower()
        
        # Check for structured data
        json_ld = soup.find_all("script", type="application/ld+json")
        if json_ld:
            data_types.append("structured_data")
            # Check for specific schema types
            for script in json_ld:
                script_text = script.string or ""
                if "MedicalBusiness" in script_text or "Hospital" in script_text:
                    data_types.append("medical_business")
                if "Person" in script_text and "Physician" in script_text:
                    data_types.append("doctor_profile")
        
        # Check for doctor/hospital listings
        if re.search(r"doctor|physician|specialist", text_content, re.I):
            if self._has_listing_pattern(soup):
                data_types.append("doctor_list")
        
        if re.search(r"hospital|clinic|medical center", text_content, re.I):
            if self._has_listing_pattern(soup):
                data_types.append("hospital_list")
        
        # Check for profile pages
        profile_indicators = ["qualification", "experience", "specialty", "practice"]
        if any(indicator in text_content for indicator in profile_indicators):
            if "doctor" in text_content or "physician" in text_content:
                data_types.append("doctor_profile")
        
        # Check for appointment booking
        if re.search(r"appointment|booking|schedule|book now", text_content, re.I):
            data_types.append("appointment_booking")
        
        # Check for reviews
        if re.search(r"review|rating|feedback", text_content, re.I):
            data_types.append("reviews")
        
        return list(set(data_types))  # Remove duplicates
    
    def _has_listing_pattern(self, soup: BeautifulSoup) -> bool:
        """Check if page has listing pattern (multiple similar items).
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            True if listing pattern detected
        """
        # Check for repeated card/item structures
        cards = soup.find_all(attrs={"class": re.compile(r"card|item|listing", re.I)})
        if len(cards) >= 3:
            return True
        
        # Check for table rows
        tables = soup.find_all("table")
        if tables:
            rows = tables[0].find_all("tr")
            if len(rows) > 3:
                return True
        
        return False
    
    def _match_keywords(self, soup: BeautifulSoup, html: str) -> Dict:
        """Match keywords in page content.
        
        Args:
            soup: BeautifulSoup object
            html: Raw HTML content
            
        Returns:
            Dictionary with "found" (list) and "scores" (dict)
        """
        found = []
        scores = {}
        
        # Extract text from different sections
        title = soup.find("title")
        title_text = title.get_text().lower() if title else ""
        
        meta_desc = soup.find("meta", attrs={"name": "description"})
        meta_text = meta_desc.get("content", "").lower() if meta_desc else ""
        
        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        headings_text = " ".join([h.get_text().lower() for h in headings])
        
        body = soup.find("body")
        body_text = body.get_text().lower() if body else ""
        
        # Score each keyword
        for keyword in self.keywords:
            score = 0.0
            
            # Title match (highest weight)
            if keyword in title_text:
                score += 10.0
                found.append(keyword)
            
            # Meta description match
            if keyword in meta_text:
                score += 8.0
                if keyword not in found:
                    found.append(keyword)
            
            # Heading match
            heading_matches = len(re.findall(rf"\b{re.escape(keyword)}\b", headings_text, re.I))
            if heading_matches > 0:
                score += 5.0 * min(heading_matches, 3)  # Cap at 3 matches
                if keyword not in found:
                    found.append(keyword)
            
            # Body text match (frequency-based)
            body_matches = len(re.findall(rf"\b{re.escape(keyword)}\b", body_text, re.I))
            if body_matches > 0:
                score += min(body_matches * 0.5, 5.0)  # Cap at 5.0
                if keyword not in found:
                    found.append(keyword)
            
            if score > 0:
                scores[keyword] = score
        
        return {"found": found, "scores": scores}
    
    def _analyze_html_structure(self, soup: BeautifulSoup) -> Dict:
        """Analyze HTML structure (forms, tables, lists, etc.).
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Dictionary with structure analysis
        """
        structure = {
            "has_forms": len(soup.find_all("form")) > 0,
            "form_count": len(soup.find_all("form")),
            "has_tables": len(soup.find_all("table")) > 0,
            "table_count": len(soup.find_all("table")),
            "has_lists": len(soup.find_all(["ul", "ol"])) > 0,
            "list_count": len(soup.find_all(["ul", "ol"])),
            "has_cards": len(soup.find_all(attrs={"class": re.compile(r"card", re.I)})) > 0,
            "card_count": len(soup.find_all(attrs={"class": re.compile(r"card", re.I)})),
            "has_images": len(soup.find_all("img")) > 0,
            "image_count": len(soup.find_all("img")),
            "has_videos": len(soup.find_all(["video", "iframe"])) > 0,
        }
        
        # Analyze forms
        forms = soup.find_all("form")
        if forms:
            structure["form_fields"] = []
            for form in forms:
                inputs = form.find_all("input")
                selects = form.find_all("select")
                textareas = form.find_all("textarea")
                structure["form_fields"].append({
                    "input_count": len(inputs),
                    "select_count": len(selects),
                    "textarea_count": len(textareas),
                })
        
        return structure


