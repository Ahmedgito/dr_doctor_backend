"""Main web crawler implementation."""

from __future__ import annotations

import time
from collections import deque
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from scrapers.base_scraper import BaseScraper
from scrapers.database.mongo_client import MongoClientManager
from scrapers.logger import logger
from scrapers.crawler.crawler_config import CrawlerConfig
from scrapers.crawler.content_analyzer import ContentAnalyzer
from scrapers.crawler.site_map_generator import SiteMapGenerator
from scrapers.crawler.sitemap_parser import SitemapParser
from scrapers.crawler.js_detector import JavaScriptDetector
from scrapers.crawler.asset_discovery import AssetDiscoverer
from scrapers.crawler.utils import (
    normalize_url,
    extract_domain,
    should_crawl_url,
    extract_links_from_html,
)


class WebCrawler(BaseScraper):
    """Web crawler that discovers and analyzes website content."""
    
    def __init__(
        self,
        mongo_client: MongoClientManager,
        config: CrawlerConfig,
    ) -> None:
        """Initialize web crawler.
        
        Args:
            mongo_client: MongoDB client manager
            config: Crawler configuration
        """
        super().__init__(
            headless=config.headless,
            timeout_ms=config.timeout_ms,
            max_retries=config.max_retries,
            wait_between_retries=config.wait_between_retries,
            disable_js=config.disable_js,
        )
        self.mongo_client = mongo_client
        self.config = config
        
        # Initialize components
        self.content_analyzer = ContentAnalyzer(keywords=config.keywords)
        self.js_detector = JavaScriptDetector()
        
        # Crawler state
        self.visited_urls: Set[str] = set()
        self.url_queue: deque = deque()
        self.robots_parser: Optional[RobotFileParser] = None
        
        # Statistics
        self.stats = {
            "total_crawled": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "total_links_found": 0,
        }
    
    def _check_robots_txt(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if allowed, False otherwise
        """
        if not self.config.respect_robots_txt:
            return True
        
        try:
            parsed = urlparse(url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            
            # Initialize robots parser if not already done
            if self.robots_parser is None or self.robots_parser.url != f"{base_url}/robots.txt":
                self.robots_parser = RobotFileParser()
                self.robots_parser.set_url(f"{base_url}/robots.txt")
                try:
                    self.robots_parser.read()
                except Exception as exc:
                    logger.debug("Could not read robots.txt for {}: {}", base_url, exc)
                    return True  # Allow if robots.txt can't be read
            
            return self.robots_parser.can_fetch("*", url)
        except Exception as exc:
            logger.debug("Error checking robots.txt for {}: {}", url, exc)
            return True  # Allow on error
    
    def _discover_urls_from_sitemap(self) -> List[str]:
        """Discover URLs from sitemap.xml files.
        
        Returns:
            List of URLs from sitemap
        """
        if not self.config.use_sitemap:
            return []
        
        urls = []
        for start_url in self.config.start_urls:
            try:
                parser = SitemapParser(start_url)
                sitemap_urls = parser.get_all_urls()
                urls.extend(sitemap_urls)
                logger.info("Found {} URLs from sitemap for {}", len(sitemap_urls), start_url)
            except Exception as exc:
                logger.warning("Failed to parse sitemap for {}: {}", start_url, exc)
        
        return list(set(urls))  # Remove duplicates
    
    def _initialize_queue(self) -> None:
        """Initialize the URL queue with start URLs and sitemap URLs."""
        # Add start URLs
        for url in self.config.start_urls:
            normalized = normalize_url(url, url)
            if normalized and should_crawl_url(normalized, self.config):
                self.url_queue.append((normalized, 0, None))  # (url, depth, parent_url)
                logger.info("Added start URL to queue: {}", normalized)
        
        # Add URLs from sitemap
        if self.config.use_sitemap:
            sitemap_urls = self._discover_urls_from_sitemap()
            for url in sitemap_urls:
                if should_crawl_url(url, self.config):
                    # Determine depth (0 for now, will be updated during crawl)
                    self.url_queue.append((url, 0, None))
                    logger.debug("Added sitemap URL to queue: {}", url)
    
    def _crawl_page(self, url: str, depth: int, parent_url: Optional[str]) -> Dict:
        """Crawl a single page.
        
        Args:
            url: URL to crawl
            depth: Current depth level
            parent_url: URL of parent page
            
        Returns:
            Dictionary with crawl results
        """
        result = {
            "url": url,
            "depth": depth,
            "parent_url": parent_url,
            "success": False,
            "links_found": [],
            "assets_found": [],
        }
        
        try:
            # Check if already crawled
            if self.mongo_client.page_crawled(url):
                logger.debug("Page already crawled: {}", url)
                self.stats["total_skipped"] += 1
                result["success"] = True
                return result
            
            # Check robots.txt
            if not self._check_robots_txt(url):
                logger.debug("URL blocked by robots.txt: {}", url)
                self.stats["total_skipped"] += 1
                return result
            
            # Load page
            self.load_page(url)
            self.wait_for("body")
            
            # Get HTML (before JS if needed)
            html_before = self.get_html()
            
            # Check if JavaScript is needed
            requires_js = False
            if self.config.detect_js and not self.config.disable_js:
                requires_js = self.js_detector.requires_javascript(html_before)
                if requires_js:
                    # Wait for JS to execute
                    self.js_detector.wait_for_content(self.page, timeout_ms=5000)
                    html_before = self.get_html()  # Get updated HTML
            
            # Extract title
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_before, "html.parser")
            title_tag = soup.find("title")
            title = title_tag.get_text().strip() if title_tag else None
            
            # Analyze content
            analysis = self.content_analyzer.analyze(html_before, url)
            
            # Discover links
            links = extract_links_from_html(html_before, url)
            filtered_links = [
                link for link in links
                if should_crawl_url(link, self.config) and self._check_robots_txt(link)
            ]
            
            # Add new links to queue if depth limit not reached
            if self.config.max_depth is None or depth < self.config.max_depth:
                for link in filtered_links:
                    if link not in self.visited_urls:
                        self.url_queue.append((link, depth + 1, url))
                        self.visited_urls.add(link)
            
            # Discover assets
            assets = []
            if self.config.discover_assets:
                asset_discoverer = AssetDiscoverer(url)
                assets = asset_discoverer.discover_assets(html_before, url)
                
                # Store assets in database
                if assets:
                    asset_dicts = [asset for asset in assets]
                    self.mongo_client.bulk_upsert_crawled_assets(asset_dicts)
            
            # Get status code
            status_code = 200  # Default, Playwright doesn't expose status easily
            
            # Prepare page data
            domain = extract_domain(url)
            page_data = {
                "url": url,
                "title": title,
                "parent_url": parent_url,
                "depth": depth,
                "domain": domain,
                "content_type": analysis.get("content_type"),
                "data_types": analysis.get("data_types", []),
                "keywords_found": analysis.get("keywords_found", []),
                "keyword_scores": analysis.get("keyword_scores", {}),
                "html_structure": analysis.get("html_structure", {}),
                "links_found": filtered_links,
                "assets_found": [asset.get("url") for asset in assets],
                "status_code": status_code,
                "crawl_status": "crawled",
                "requires_js": requires_js,
            }
            
            # Store in database
            self.mongo_client.upsert_crawled_page(page_data)
            self.mongo_client.mark_page_crawled(url)
            
            result["success"] = True
            result["links_found"] = filtered_links
            result["assets_found"] = [asset.get("url") for asset in assets]
            
            self.stats["total_crawled"] += 1
            self.stats["total_links_found"] += len(filtered_links)
            
            logger.info(
                "Crawled page: {} (depth: {}, links: {}, keywords: {})",
                url,
                depth,
                len(filtered_links),
                len(analysis.get("keywords_found", [])),
            )
        
        except Exception as exc:
            logger.warning("Failed to crawl page {}: {}", url, exc)
            self.stats["total_failed"] += 1
            
            # Mark as failed in database
            domain = extract_domain(url)
            self.mongo_client.upsert_crawled_page({
                "url": url,
                "domain": domain,
                "depth": depth,
                "parent_url": parent_url,
                "crawl_status": "failed",
                "error_message": str(exc),
            })
            self.mongo_client.mark_page_failed(url, str(exc))
        
        return result
    
    def _generate_site_map(self, domain: str) -> None:
        """Generate and store site map for a domain.
        
        Args:
            domain: Domain name
        """
        try:
            # Get all crawled pages for this domain
            pages = self.mongo_client.get_crawled_pages(domain, status="crawled")
            
            if not pages:
                logger.warning("No crawled pages found for domain: {}", domain)
                return
            
            # Convert to format expected by SiteMapGenerator
            page_list = [
                {
                    "url": page.get("url"),
                    "depth": page.get("depth", 0),
                    "parent_url": page.get("parent_url"),
                    "title": page.get("title"),
                    "content_type": page.get("content_type"),
                }
                for page in pages
            ]
            
            # Generate site map
            root_url = self.config.start_urls[0] if self.config.start_urls else ""
            generator = SiteMapGenerator(domain, root_url)
            site_map = generator.generate_site_map(page_list)
            
            # Store in database
            self.mongo_client.upsert_site_map(site_map)
            
            logger.info(
                "Generated site map for {}: {} pages, max depth: {}",
                domain,
                site_map["total_pages"],
                site_map["max_depth"],
            )
        except Exception as exc:
            logger.warning("Failed to generate site map for {}: {}", domain, exc)
    
    def crawl(self) -> Dict:
        """Start crawling process.
        
        Returns:
            Dictionary with crawl statistics
        """
        logger.info("Starting web crawler with config: {}", self.config)
        
        # Initialize queue
        self._initialize_queue()
        
        # Mark start URLs as visited
        for url in self.config.start_urls:
            normalized = normalize_url(url, url)
            self.visited_urls.add(normalized)
        
        # Crawl loop
        while self.url_queue:
            # Check max pages limit
            if self.config.max_pages and self.stats["total_crawled"] >= self.config.max_pages:
                logger.info("Reached max pages limit: {}", self.config.max_pages)
                break
            
            # Get next URL from queue
            url, depth, parent_url = self.url_queue.popleft()
            
            # Check depth limit
            if self.config.max_depth is not None and depth > self.config.max_depth:
                continue
            
            # Crawl the page
            self._crawl_page(url, depth, parent_url)
            
            # Polite delay
            if self.config.delay_between_requests > 0:
                time.sleep(self.config.delay_between_requests)
        
        # Generate site maps for each domain
        domains = set()
        for start_url in self.config.start_urls:
            domains.add(extract_domain(start_url))
        
        for domain in domains:
            self._generate_site_map(domain)
        
        logger.info(
            "Crawling completed. Stats: crawled={}, failed={}, skipped={}, links_found={}",
            self.stats["total_crawled"],
            self.stats["total_failed"],
            self.stats["total_skipped"],
            self.stats["total_links_found"],
        )
        
        return self.stats


