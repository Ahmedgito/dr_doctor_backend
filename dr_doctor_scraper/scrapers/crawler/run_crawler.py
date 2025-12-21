"""CLI entry point for web crawler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent directory to path to allow imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scrapers.database.mongo_client import MongoClientManager
from scrapers.logger import logger
from scrapers.crawler.crawler_config import CrawlerConfig
from scrapers.crawler.web_crawler import WebCrawler
from scrapers.crawler.multi_threaded_crawler import MultiThreadedWebCrawler
from scrapers.crawler.distributed_crawler import DistributedWebCrawler


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Web crawler for discovering and analyzing website content")
    
    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="Starting URL(s), comma-separated for multiple URLs",
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default="",
        help="Keywords to search for, comma-separated",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum crawl depth (default: unlimited)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum number of pages to crawl (default: unlimited)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="Number of threads for parallel crawling (default: 1, single-threaded)",
    )
    parser.add_argument(
        "--distributed",
        action="store_true",
        help="Enable distributed crawling mode",
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help="Instance ID for distributed crawling (auto-generated if not provided)",
    )
    parser.add_argument(
        "--no-sitemap",
        action="store_true",
        help="Disable sitemap.xml parsing",
    )
    parser.add_argument(
        "--no-js-detection",
        action="store_true",
        help="Disable JavaScript rendering detection",
    )
    parser.add_argument(
        "--no-assets",
        action="store_true",
        help="Disable asset discovery",
    )
    parser.add_argument(
        "--no-robots",
        action="store_true",
        help="Don't respect robots.txt",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run browser with visible UI",
    )
    parser.add_argument(
        "--test-db",
        action="store_true",
        help="Use test database",
    )
    
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Parse URLs
    start_urls = [url.strip() for url in args.url.split(",") if url.strip()]
    if not start_urls:
        logger.error("No valid URLs provided")
        sys.exit(1)
    
    # Parse keywords
    keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()] if args.keywords else []
    
    # Create configuration
    config = CrawlerConfig(
        start_urls=start_urls,
        keywords=keywords,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        num_threads=args.threads,
        respect_robots_txt=not args.no_robots,
        delay_between_requests=args.delay,
        use_sitemap=not args.no_sitemap,
        detect_js=not args.no_js_detection,
        discover_assets=not args.no_assets,
        distributed=args.distributed,
        instance_id=args.instance_id,
        headless=args.headless,
    )
    
    # Initialize MongoDB client
    try:
        mongo_client = MongoClientManager(test_db=args.test_db)
    except Exception as exc:
        logger.error("Failed to connect to MongoDB: {}", exc)
        sys.exit(1)
    
    try:
        # Choose crawler type
        if args.distributed:
            logger.info("Starting distributed crawler")
            crawler = DistributedWebCrawler(mongo_client, config)
            stats = crawler.crawl()
        elif args.threads > 1:
            logger.info("Starting multi-threaded crawler with {} threads", args.threads)
            crawler = MultiThreadedWebCrawler(mongo_client, config)
            stats = crawler.crawl()
        else:
            logger.info("Starting single-threaded crawler")
            crawler = WebCrawler(mongo_client, config)
            with crawler:
                stats = crawler.crawl()
        
        # Print summary
        logger.info("=" * 60)
        logger.info("Crawling Summary:")
        logger.info("  Total crawled: {}", stats.get("total_crawled", 0))
        logger.info("  Total failed: {}", stats.get("total_failed", 0))
        logger.info("  Total skipped: {}", stats.get("total_skipped", 0))
        logger.info("  Total links found: {}", stats.get("total_links_found", 0))
        logger.info("=" * 60)
    
    except KeyboardInterrupt:
        logger.info("Crawling interrupted by user")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Crawling failed: {}", exc)
        sys.exit(1)
    finally:
        mongo_client.close()


if __name__ == "__main__":
    main()


