"""Web crawler module for discovering and analyzing website content."""

from scrapers.crawler.web_crawler import WebCrawler
from scrapers.crawler.crawler_config import CrawlerConfig
from scrapers.crawler.multi_threaded_crawler import MultiThreadedWebCrawler
from scrapers.crawler.distributed_crawler import DistributedWebCrawler

__all__ = [
    "WebCrawler",
    "CrawlerConfig",
    "MultiThreadedWebCrawler",
    "DistributedWebCrawler",
]

