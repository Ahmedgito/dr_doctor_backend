"""Distributed web crawler implementation using MongoDB as shared queue."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from scrapers.logger import logger
from scrapers.crawler.web_crawler import WebCrawler
from scrapers.crawler.crawler_config import CrawlerConfig
from scrapers.database.mongo_client import MongoClientManager
from scrapers.crawler.utils import extract_domain, normalize_url, should_crawl_url


class DistributedWebCrawler:
    """Distributed web crawler using MongoDB as shared queue."""
    
    def __init__(
        self,
        mongo_client: MongoClientManager,
        config: CrawlerConfig,
    ) -> None:
        """Initialize distributed web crawler.
        
        Args:
            mongo_client: MongoDB client manager
            config: Crawler configuration (must have instance_id for distributed mode)
        """
        self.mongo_client = mongo_client
        self.config = config
        
        # Generate instance ID if not provided
        self.instance_id = config.instance_id or f"crawler-{uuid.uuid4().hex[:8]}"
        
        # Heartbeat interval (seconds)
        self.heartbeat_interval = 30
        self.last_heartbeat = datetime.utcnow()
        
        # Statistics
        self.stats = {
            "total_crawled": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "total_links_found": 0,
        }
    
    def _acquire_url_lock(self, url: str) -> bool:
        """Acquire distributed lock for a URL.
        
        Args:
            url: URL to lock
            
        Returns:
            True if lock acquired, False otherwise
        """
        try:
            # Try to insert lock document
            lock_doc = {
                "url": url,
                "instance_id": self.instance_id,
                "locked_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(minutes=5),  # 5 minute lock
            }
            
            self.mongo_client.crawl_locks.insert_one(lock_doc)
            return True
        except Exception:
            # Lock already exists (duplicate key error)
            # Check if lock is expired
            existing = self.mongo_client.crawl_locks.find_one({"url": url})
            if existing:
                expires_at = existing.get("expires_at")
                if expires_at and datetime.utcnow() > expires_at:
                    # Lock expired, remove it and try again
                    self.mongo_client.crawl_locks.delete_one({"url": url})
                    try:
                        self.mongo_client.crawl_locks.insert_one(lock_doc)
                        return True
                    except Exception:
                        return False
            return False
    
    def _release_url_lock(self, url: str) -> None:
        """Release distributed lock for a URL.
        
        Args:
            url: URL to unlock
        """
        try:
            self.mongo_client.crawl_locks.delete_one({
                "url": url,
                "instance_id": self.instance_id,
            })
        except Exception:
            pass
    
    def _cleanup_expired_locks(self) -> None:
        """Clean up expired locks from other instances."""
        try:
            self.mongo_client.crawl_locks.delete_many({
                "expires_at": {"$lt": datetime.utcnow()},
            })
        except Exception:
            pass
    
    def _get_next_url_from_queue(self) -> Optional[tuple]:
        """Get next URL from distributed queue.
        
        Returns:
            Tuple of (url, depth, parent_url) or None
        """
        try:
            # Find and claim a URL from queue
            result = self.mongo_client.crawl_queue.find_one_and_update(
                {
                    "status": "pending",
                    "domain": {"$in": [extract_domain(url) for url in self.config.start_urls]},
                },
                {
                    "$set": {
                        "status": "processing",
                        "instance_id": self.instance_id,
                        "claimed_at": datetime.utcnow(),
                    }
                },
                sort=[("priority", -1), ("_id", 1)],  # Higher priority first
            )
            
            if result:
                return (
                    result["url"],
                    result.get("depth", 0),
                    result.get("parent_url"),
                )
        except Exception as exc:
            logger.debug("Error getting URL from queue: {}", exc)
        
        return None
    
    def _add_url_to_queue(self, url: str, depth: int, parent_url: Optional[str], priority: int = 0) -> None:
        """Add URL to distributed queue.
        
        Args:
            url: URL to add
            depth: Depth level
            parent_url: Parent URL
            priority: Priority (higher = processed first)
        """
        try:
            domain = extract_domain(url)
            self.mongo_client.crawl_queue.update_one(
                {"url": url},
                {
                    "$set": {
                        "url": url,
                        "domain": domain,
                        "depth": depth,
                        "parent_url": parent_url,
                        "status": "pending",
                        "priority": priority,
                        "created_at": datetime.utcnow(),
                    }
                },
                upsert=True,
            )
        except Exception:
            pass
    
    def _mark_url_complete(self, url: str) -> None:
        """Mark URL as complete in queue.
        
        Args:
            url: URL to mark as complete
        """
        try:
            self.mongo_client.crawl_queue.update_one(
                {"url": url},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.utcnow(),
                    }
                }
            )
        except Exception:
            pass
    
    def _mark_url_failed(self, url: str) -> None:
        """Mark URL as failed in queue.
        
        Args:
            url: URL to mark as failed
        """
        try:
            self.mongo_client.crawl_queue.update_one(
                {"url": url},
                {
                    "$set": {
                        "status": "failed",
                        "failed_at": datetime.utcnow(),
                    }
                }
            )
        except Exception:
            pass
    
    def _send_heartbeat(self) -> None:
        """Send heartbeat to indicate this instance is alive."""
        try:
            self.mongo_client.crawl_jobs.update_one(
                {"instance_id": self.instance_id},
                {
                    "$set": {
                        "instance_id": self.instance_id,
                        "last_heartbeat": datetime.utcnow(),
                        "status": "running",
                    }
                },
                upsert=True,
            )
            self.last_heartbeat = datetime.utcnow()
        except Exception:
            pass
    
    def _initialize_queue(self) -> None:
        """Initialize the distributed queue with start URLs and sitemap URLs."""
        # Add start URLs
        for url in self.config.start_urls:
            normalized = normalize_url(url, url)
            if normalized and should_crawl_url(normalized, self.config):
                self._add_url_to_queue(normalized, 0, None, priority=10)
                logger.info("Added start URL to queue: {}", normalized)
        
        # Add URLs from sitemap
        if self.config.use_sitemap:
            from scrapers.crawler.sitemap_parser import SitemapParser
            for start_url in self.config.start_urls:
                try:
                    parser = SitemapParser(start_url)
                    sitemap_urls = parser.get_all_urls()
                    for url in sitemap_urls:
                        if should_crawl_url(url, self.config):
                            self._add_url_to_queue(url, 0, None, priority=5)
                    logger.info("Added {} URLs from sitemap for {}", len(sitemap_urls), start_url)
                except Exception as exc:
                    logger.warning("Failed to parse sitemap for {}: {}", start_url, exc)
    
    def crawl(self) -> Dict:
        """Start distributed crawling process.
        
        Returns:
            Dictionary with crawl statistics
        """
        logger.info("Starting distributed web crawler (instance: {})", self.instance_id)
        
        # Register this instance
        self._send_heartbeat()
        
        # Initialize queue
        self._initialize_queue()
        
        # Create crawler instance
        crawler = WebCrawler(self.mongo_client, self.config)
        
        with crawler:
            # Main crawl loop
            consecutive_empty = 0
            max_consecutive_empty = 10  # Stop after 10 consecutive empty queue checks
            
            while True:
                # Send heartbeat periodically
                if (datetime.utcnow() - self.last_heartbeat).total_seconds() > self.heartbeat_interval:
                    self._send_heartbeat()
                    self._cleanup_expired_locks()
                
                # Check max pages limit
                if self.config.max_pages and self.stats["total_crawled"] >= self.config.max_pages:
                    logger.info("Reached max pages limit: {}", self.config.max_pages)
                    break
                
                # Get next URL from queue
                url_data = self._get_next_url_from_queue()
                
                if not url_data:
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        logger.info("Queue empty for {} iterations, stopping", max_consecutive_empty)
                        break
                    time.sleep(1)
                    continue
                
                consecutive_empty = 0
                url, depth, parent_url = url_data
                
                # Check depth limit
                if self.config.max_depth is not None and depth > self.config.max_depth:
                    self._mark_url_complete(url)
                    continue
                
                # Acquire lock
                if not self._acquire_url_lock(url):
                    # Could not acquire lock, put URL back
                    self._add_url_to_queue(url, depth, parent_url)
                    time.sleep(0.1)
                    continue
                
                try:
                    # Check if already crawled
                    if self.mongo_client.page_crawled(url):
                        self.stats["total_skipped"] += 1
                        self._mark_url_complete(url)
                        self._release_url_lock(url)
                        continue
                    
                    # Crawl the page
                    result = crawler._crawl_page(url, depth, parent_url)
                    
                    if result["success"]:
                        self.stats["total_crawled"] += 1
                        self.stats["total_links_found"] += len(result.get("links_found", []))
                        self._mark_url_complete(url)
                        
                        # Add new links to queue
                        if self.config.max_depth is None or depth < self.config.max_depth:
                            for link in result.get("links_found", []):
                                self._add_url_to_queue(link, depth + 1, url, priority=0)
                    else:
                        self.stats["total_failed"] += 1
                        self._mark_url_failed(url)
                    
                    # Polite delay
                    if self.config.delay_between_requests > 0:
                        time.sleep(self.config.delay_between_requests)
                
                except Exception as exc:
                    logger.error("Error crawling {}: {}", url, exc)
                    self.stats["total_failed"] += 1
                    self._mark_url_failed(url)
                
                finally:
                    self._release_url_lock(url)
        
        # Generate site maps
        from scrapers.crawler.site_map_generator import SiteMapGenerator
        
        domains = set()
        for start_url in self.config.start_urls:
            domains.add(extract_domain(start_url))
        
        for domain in domains:
            try:
                pages = self.mongo_client.get_crawled_pages(domain, status="crawled")
                if pages:
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
                    
                    root_url = self.config.start_urls[0] if self.config.start_urls else ""
                    generator = SiteMapGenerator(domain, root_url)
                    site_map = generator.generate_site_map(page_list)
                    self.mongo_client.upsert_site_map(site_map)
                    
                    logger.info("Generated site map for {}: {} pages", domain, site_map["total_pages"])
            except Exception as exc:
                logger.warning("Failed to generate site map for {}: {}", domain, exc)
        
        logger.info(
            "Distributed crawling completed (instance: {}). Stats: crawled={}, failed={}, skipped={}, links_found={}",
            self.instance_id,
            self.stats["total_crawled"],
            self.stats["total_failed"],
            self.stats["total_skipped"],
            self.stats["total_links_found"],
        )
        
        return self.stats


