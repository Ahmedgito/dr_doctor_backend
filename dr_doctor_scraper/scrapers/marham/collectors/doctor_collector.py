"""Doctor card collection logic with Load More handling."""

from __future__ import annotations

import time
from typing import List
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.logger import logger


class DoctorCollector:
    """Collects doctor cards from hospital pages, handling dynamic loading."""

    @staticmethod
    def collect_doctor_cards_from_hospital(scraper: BaseScraper, hospital_url: str) -> List[BeautifulSoup]:
        """Load the hospital page and attempt to collect all doctor cards.

        Strategy:
        - Load initial page and gather cards.
        - If a "Load More" button exists, click it repeatedly until it disappears
          or a safety limit is reached. Wait for loading buffer to disappear.
        - Return list of card elements (BeautifulSoup Tag objects).

        Args:
            scraper: BaseScraper instance with active page
            hospital_url: URL of the hospital page to scrape

        Returns:
            List of BeautifulSoup Tag objects representing doctor cards
        """
        scraper.load_page(hospital_url)
        scraper.wait_for("body")
        html = scraper.get_html()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".row.shadow-card")

        # If the page uses a client-side "Load More" button, try to click it via Playwright
        try:
            if scraper.page and scraper.page.query_selector("#loadMore"):
                logger.info("'Load More' detected on {} — clicking until exhausted", hospital_url)
                clicks = 0
                while clicks < 20 and scraper.page.query_selector("#loadMore"):
                    try:
                        scraper.page.click("#loadMore")
                        logger.info("Load More button clicked, waiting for content to load...")
                        
                        # Wait for loading buffer to appear and disappear
                        time.sleep(0.5)
                        
                        # Wait for loading buffer to disappear (up to 30 seconds)
                        max_wait = 30
                        waited = 0
                        loading_found = False
                        
                        while waited < max_wait:
                            # Check for various loading indicators
                            loading_spinner = scraper.page.query_selector(
                                ".loader, .loading, .spinner, [class*='load'], [class*='spin']"
                            )
                            
                            if loading_spinner:
                                loading_found = True
                                logger.debug("Loading indicator detected, waiting for it to disappear...")
                                time.sleep(1)
                                waited += 1
                            else:
                                if loading_found:
                                    logger.info("Loading complete after {} seconds", waited)
                                break
                            
                            if waited % 5 == 0:
                                logger.info("Still waiting for content to load... ({}/{}s)", waited, max_wait)
                        
                        # Wait additional time for DOM to settle
                        time.sleep(1)
                        
                        # Try to wait for network idle
                        try:
                            scraper.page.wait_for_load_state("networkidle", timeout=5000)
                        except Exception:
                            pass
                        
                        time.sleep(0.5)
                        html = scraper.get_html()
                        soup = BeautifulSoup(html, "html.parser")
                        new_cards = soup.select(".row.shadow-card")
                        
                        # If no new cards were added, stop clicking
                        if len(new_cards) <= len(cards):
                            logger.info("No new cards loaded after clicking. Stopping Load More.")
                            break
                        
                        cards = new_cards
                        clicks += 1
                        logger.info("Load More click #{}: {} total cards collected", clicks, len(cards))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Clicking Load More failed on {}: {}", hospital_url, exc)
                        break

        except Exception:
            # If Playwright interactions are not possible for some reason, fall back to initial cards
            logger.debug("Could not interact with Load More button for {} — proceeding with initial cards", hospital_url)

        return cards

