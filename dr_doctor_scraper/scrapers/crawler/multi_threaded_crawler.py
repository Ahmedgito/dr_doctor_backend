"""Multi-threaded web crawler implementation."""

from __future__ import annotations

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, Empty
from typing import Dict, List, Optional, Set

from scrapers.logger import logger
from scrapers.crawler.web_crawler import WebCrawler
from scrapers.crawler.crawler_config import CrawlerConfig
from scrapers.database.mongo_client import MongoClientManager
from scrapers.crawler.utils import extract_domain, normalize_url, should_crawl_url


class MultiThreadedWebCrawler:
    """Multi-threaded web crawler for parallel page processing."""
    
    def __init__(
        self,
        mongo_client: MongoClientManager,
        config: CrawlerConfig,
    ) -> None:
        """Initialize multi-threaded web crawler.
        
        Args:
            mongo_client: MongoDB client manager (thread-safe)
            config: Crawler configuration
        """
        self.mongo_client = mongo_client
        self.config = config
        
        # Thread-safe queue and visited set
        self.url_queue: Queue = Queue()
        self.visited_urls: Set[str] = set()
        self.visited_lock = threading.Lock()
        
        # Statistics (thread-safe)
        self.stats_lock = threading.Lock()
        self.stats = {
            "total_crawled": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "total_links_found": 0,
        }
        
        # Worker threads
        self.num_threads = config.num_threads if config.num_threads > 1 else 1
    
    def _worker(self, worker_id: int) -> Dict:
        """Worker thread function.
        
        Args:
            worker_id: Unique worker thread ID
            
        Returns:
            Dictionary with worker statistics
        """
        worker_stats = {
            "total_crawled": 0,
            "total_failed": 0,
            "total_skipped": 0,
            "total_links_found": 0,
        }
        
        try:
            # Create crawler instance for this thread
            crawler = WebCrawler(self.mongo_client, self.config)
            
            with crawler:
                while True:
                    try:
                        # Get URL from queue (with timeout to allow checking if done)
                        try:
                            url, depth, parent_url = self.url_queue.get(timeout=1)
                        except Empty:
                            # Check if we should continue
                            if self.url_queue.empty():
                                # Wait a bit more in case other threads add URLs
                                time.sleep(0.5)
                                if self.url_queue.empty():
                                    break
                            continue
                        
                        # Check depth limit
                        if self.config.max_depth is not None and depth > self.config.max_depth:
                            continue
                        
                        # Check max pages limit
                        with self.stats_lock:
                            if self.config.max_pages and self.stats["total_crawled"] >= self.config.max_pages:
                                # Put URL back and exit
                                self.url_queue.put((url, depth, parent_url))
                                break
                        
                        # Check if already visited (thread-safe)
                        with self.visited_lock:
                            if url in self.visited_urls:
                                worker_stats["total_skipped"] += 1
                                continue
                            self.visited_urls.add(url)
                        
                        # Crawl the page
                        result = crawler._crawl_page(url, depth, parent_url)
                        
                        if result["success"]:
                            worker_stats["total_crawled"] += 1
                            worker_stats["total_links_found"] += len(result.get("links_found", []))
                            
                            # Add new links to queue
                            if self.config.max_depth is None or depth < self.config.max_depth:
                                for link in result.get("links_found", []):
                                    with self.visited_lock:
                                        if link not in self.visited_urls:
                                            self.url_queue.put((link, depth + 1, url))
                                            self.visited_urls.add(link)
                        else:
                            worker_stats["total_failed"] += 1
                        
                        # Polite delay
                        if self.config.delay_between_requests > 0:
                            time.sleep(self.config.delay_between_requests)
                        
                        # Mark task as done
                        self.url_queue.task_done()
                        
                    except Exception as exc:
                        logger.error("[Worker {}] Error processing URL: {}", worker_id, exc)
                        worker_stats["total_failed"] += 1
                        self.url_queue.task_done()
        
        except Exception as exc:
            logger.error("[Worker {}] Worker thread failed: {}", worker_id, exc)
        
        logger.info("[Worker {}] Finished. Stats: {}", worker_id, worker_stats)
        return worker_stats
    
    def _initialize_queue(self) -> None:
        """Initialize the URL queue with start URLs and sitemap URLs."""
        # Add start URLs
        for url in self.config.start_urls:
            normalized = normalize_url(url, url)
            if normalized and should_crawl_url(normalized, self.config):
                self.url_queue.put((normalized, 0, None))
                self.visited_urls.add(normalized)
                logger.info("Added start URL to queue: {}", normalized)
        
        # Add URLs from sitemap
        if self.config.use_sitemap:
            from scrapers.crawler.sitemap_parser import SitemapParser
            for start_url in self.config.start_urls:
                try:
                    parser = SitemapParser(start_url)
                    sitemap_urls = parser.get_all_urls()
                    for url in sitemap_urls:
                        if should_crawl_url(url, self.config) and url not in self.visited_urls:
                            self.url_queue.put((url, 0, None))
                            self.visited_urls.add(url)
                    logger.info("Added {} URLs from sitemap for {}", len(sitemap_urls), start_url)
                except Exception as exc:
                    logger.warning("Failed to parse sitemap for {}: {}", start_url, exc)
    
    def crawl(self) -> Dict:
        """Start multi-threaded crawling process.
        
        Returns:
            Dictionary with crawl statistics
        """
        logger.info("Starting multi-threaded web crawler with {} threads", self.num_threads)
        
        # Initialize queue
        self._initialize_queue()
        
        # Start worker threads
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [
                executor.submit(self._worker, i)
                for i in range(self.num_threads)
            ]
            
            # Wait for all workers to complete
            for future in as_completed(futures):
                try:
                    worker_stats = future.result()
                    # Aggregate statistics
                    with self.stats_lock:
                        self.stats["total_crawled"] += worker_stats["total_crawled"]
                        self.stats["total_failed"] += worker_stats["total_failed"]
                        self.stats["total_skipped"] += worker_stats["total_skipped"]
                        self.stats["total_links_found"] += worker_stats["total_links_found"]
                except Exception as exc:
                    logger.error("Worker thread failed: {}", exc)
        
        # Generate site maps for each domain
        from scrapers.crawler.site_map_generator import SiteMapGenerator
        from scrapers.crawler.utils import extract_domain
        
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
                    
                    logger.info(
                        "Generated site map for {}: {} pages",
                        domain,
                        site_map["total_pages"],
                    )
            except Exception as exc:
                logger.warning("Failed to generate site map for {}: {}", domain, exc)
        
        logger.info(
            "Multi-threaded crawling completed. Stats: crawled={}, failed={}, skipped={}, links_found={}",
            self.stats["total_crawled"],
            self.stats["total_failed"],
            self.stats["total_skipped"],
            self.stats["total_links_found"],
        )
        
        return self.stats


