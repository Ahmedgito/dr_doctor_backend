"""JavaScript rendering detection for crawled pages."""

from __future__ import annotations

from typing import Optional
from bs4 import BeautifulSoup

from scrapers.logger import logger


class JavaScriptDetector:
    """Detects if a page requires JavaScript to render content."""
    
    def __init__(self):
        """Initialize JavaScript detector."""
        pass
    
    def requires_javascript(self, html_before_js: str, html_after_js: Optional[str] = None) -> bool:
        """Detect if page requires JavaScript rendering.
        
        Args:
            html_before_js: HTML content before JavaScript execution
            html_after_js: HTML content after JavaScript execution (optional)
            
        Returns:
            True if JavaScript is required
        """
        soup_before = BeautifulSoup(html_before_js, "html.parser")
        
        # Check for empty or minimal body content
        body = soup_before.find("body")
        if body:
            body_text = body.get_text().strip()
            # If body is very short, likely needs JS
            if len(body_text) < 100:
                # Check for JS framework indicators
                if self._has_js_framework_indicators(soup_before):
                    return True
        
        # Check for common SPA patterns
        if self._has_spa_patterns(soup_before):
            return True
        
        # If we have after-JS HTML, compare
        if html_after_js:
            soup_after = BeautifulSoup(html_after_js, "html.parser")
            body_after = soup_after.find("body")
            if body_after:
                body_text_after = body_after.get_text().strip()
                # If content significantly increased, JS was needed
                if len(body_text_after) > len(body_text) * 2:
                    return True
        
        return False
    
    def _has_js_framework_indicators(self, soup: BeautifulSoup) -> bool:
        """Check for JavaScript framework indicators.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            True if framework indicators found
        """
        # Check script tags for framework names
        scripts = soup.find_all("script")
        framework_keywords = [
            "react", "vue", "angular", "ember", "backbone",
            "next.js", "nuxt", "gatsby",
            "__NEXT_DATA__", "__REACT_DEVTOOLS__",
            "ng-app", "data-reactroot", "data-vue",
        ]
        
        for script in scripts:
            script_src = script.get("src", "").lower()
            script_text = (script.string or "").lower()
            
            for keyword in framework_keywords:
                if keyword in script_src or keyword in script_text:
                    return True
        
        # Check for root divs with framework classes/ids
        body = soup.find("body")
        if body:
            root_divs = body.find_all("div", limit=5)
            for div in root_divs:
                div_id = div.get("id", "").lower()
                div_class = " ".join(div.get("class", [])).lower()
                
                if any(kw in div_id or kw in div_class for kw in ["app", "root", "main", "container"]):
                    # Check if it's empty or has minimal content
                    if len(div.get_text().strip()) < 50:
                        return True
        
        return False
    
    def _has_spa_patterns(self, soup: BeautifulSoup) -> bool:
        """Check for Single Page Application patterns.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            True if SPA patterns detected
        """
        # Check for router indicators
        router_keywords = ["router", "route", "routing", "history", "hash"]
        
        scripts = soup.find_all("script")
        for script in scripts:
            script_text = (script.string or "").lower()
            if any(kw in script_text for kw in router_keywords):
                return True
        
        # Check for data attributes that suggest dynamic content
        body = soup.find("body")
        if body:
            # Look for empty containers that might be populated by JS
            empty_containers = body.find_all(
                ["div", "section", "main"],
                string=lambda text: text and len(text.strip()) < 10
            )
            if len(empty_containers) > 2:
                return True
        
        return False
    
    def wait_for_content(self, page, timeout_ms: int = 5000) -> bool:
        """Wait for dynamic content to load using Playwright.
        
        Args:
            page: Playwright Page object
            timeout_ms: Timeout in milliseconds
            
        Returns:
            True if content loaded successfully
        """
        try:
            # Wait for network to be idle
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            
            # Wait a bit more for any lazy-loaded content
            page.wait_for_timeout(1000)
            
            return True
        except Exception as exc:
            logger.debug("Timeout waiting for content: {}", exc)
            return False


