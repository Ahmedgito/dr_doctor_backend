from __future__ import annotations

import argparse
from typing import Dict

from scrapers.database.mongo_client import MongoClientManager
from scrapers.logger import logger
from scrapers.marham_scraper import MarhamScraper
from scrapers.oladoc_scraper import OladocScraper


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dr.Doctor web scrapers")
    parser.add_argument(
        "--site",
        choices=["oladoc", "marham", "all"],
        required=True,
        help="Which site to scrape",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (default)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Run browser with visible UI",
    )
    parser.set_defaults(headless=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of profiles per site (for testing)",
    )
    parser.add_argument(
        "--disable-js",
        action="store_true",
        help="Disable JavaScript for faster scraping (use if site works without JS)",
    )
    parser.add_argument(
        "--test-db",
        action="store_true",
        help="Use test database (dr_doctor_test) instead of production",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="Number of worker threads for parallel processing (default: 1, use 4-8 for faster scraping)",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=[0, 1, 2, 3],
        default=None,
        help="Run only a specific step (0=collect cities, 1=collect hospitals, 2=enrich hospitals, 3=process doctors). Default: run all steps",
    )
    return parser.parse_args()


def run_for_site(site: str, mongo: MongoClientManager, headless: bool, limit: int | None, disable_js: bool = False, num_threads: int = 1, step: int | None = None) -> Dict[str, int]:
    stats = {"total": 0, "inserted": 0, "skipped": 0}

    if site == "oladoc":
        logger.info("Running Oladoc scraper")
        with OladocScraper(mongo_client=mongo, headless=headless, disable_js=disable_js) as scraper:
            stats = scraper.scrape(limit=limit)
    elif site == "marham":
        if num_threads > 1:
            logger.info(f"Running Marham scraper with {num_threads} threads (multi-threaded mode)")
            from scrapers.marham.multi_threaded_scraper import MultiThreadedMarhamScraper
            scraper = MultiThreadedMarhamScraper(
                mongo_client=mongo,
                num_threads=num_threads,
                headless=headless,
            )
            stats = scraper.scrape(limit=limit, step=step)
        else:
            logger.info("Running Marham scraper (single-threaded mode)")
            with MarhamScraper(mongo_client=mongo, headless=headless, disable_js=disable_js) as scraper:
                stats = scraper.scrape(limit=limit, step=step)
    else:
        raise ValueError(f"Unsupported site: {site}")

    logger.info(
        "Stats for {}: total={}, inserted={}, skipped={}",
        site,
        stats["total"],
        stats["inserted"],
        stats["skipped"],
    )
    return stats


def main() -> None:
    args = parse_args()
    logger.info("Starting scraper with args: {}", args)

    # Use test database if requested
    mongo = MongoClientManager(test_db=args.test_db)

    try:
        grand_total = {"total": 0, "inserted": 0, "skipped": 0}

        sites = ["oladoc", "marham"] if args.site == "all" else [args.site]

        for site in sites:
            stats = run_for_site(site, mongo, args.headless, args.limit, args.disable_js, args.threads, args.step)
            for key in grand_total:
                grand_total[key] += stats.get(key, 0)

        logger.info(
            "=== Scraping finished ===\nTotal scraped: {}\nTotal inserted: {}\nTotal skipped: {}",
            grand_total["total"],
            grand_total["inserted"],
            grand_total["skipped"],
        )
    finally:
        mongo.close()


if __name__ == "__main__":  # pragma: no cover
    main()
