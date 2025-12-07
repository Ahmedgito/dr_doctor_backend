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
                initial_card_count = len(cards)
                logger.info("Initial cards found: {}", initial_card_count)
                
                clicks = 0
                max_clicks = 20
                
                while clicks < max_clicks:
                    load_more_button = scraper.page.query_selector("#loadMore")
                    if not load_more_button:
                        logger.info("Load More button no longer visible. All content loaded.")
                        break
                    
                    # Check if button is visible and enabled
                    is_visible = load_more_button.is_visible()
                    is_enabled = load_more_button.is_enabled()
                    
                    if not is_visible or not is_enabled:
                        logger.info("Load More button is not clickable (visible={}, enabled={})", is_visible, is_enabled)
                        break
                    
                    try:
                        logger.info("=" * 60)
                        logger.info("Clicking Load More button (click #{})...", clicks + 1)
                        
                        # Get card count before clicking
                        cards_before = len(cards)
                        logger.info("Cards before click: {}", cards_before)
                        
                        # Click the button
                        load_more_button.click()
                        logger.info("Button clicked! Waiting for content to load...")
                        
                        # Wait a moment for the click to register
                        time.sleep(0.5)
                        
                        # Wait for loading indicators to appear and disappear, or new cards to load
                        max_wait = 5  # Reduced to 5 seconds as requested
                        waited = 0
                        loading_detected = False
                        loading_visible = False
                        check_interval = 0.5  # Check every 0.5 seconds
                        
                        logger.info("Monitoring loading state (max wait: {}s)...", max_wait)
                        
                        while waited < max_wait:
                            # Check if new cards have been loaded (early exit if content is ready)
                            try:
                                html_check = scraper.get_html()
                                soup_check = BeautifulSoup(html_check, "html.parser")
                                current_cards = soup_check.select(".row.shadow-card")
                                if len(current_cards) > cards_before:
                                    logger.info("✓ New cards detected! ({}) cards now (was {}). Content loaded after {:.1f} seconds", 
                                              len(current_cards), cards_before, waited)
                                    break
                            except Exception:
                                pass  # Continue waiting if check fails
                            
                            # Check for various loading indicators
                            loading_selectors = [
                                ".loader",
                                ".loading", 
                                ".spinner",
                                "[class*='load']",
                                "[class*='spin']",
                                "[class*='Loading']",
                                "[id*='load']",
                                "[id*='Loading']"
                            ]
                            
                            loading_elements = []
                            for selector in loading_selectors:
                                try:
                                    elements = scraper.page.query_selector_all(selector)
                                    visible_elements = [e for e in elements if e.is_visible()]
                                    if visible_elements:
                                        loading_elements.extend(visible_elements)
                                except Exception:
                                    pass
                            
                            if loading_elements:
                                if not loading_detected:
                                    logger.info("✓ Loading indicator detected! Waiting for it to disappear...")
                                    loading_detected = True
                                loading_visible = True
                                time.sleep(check_interval)
                                waited += check_interval
                            else:
                                if loading_visible:
                                    logger.info("✓ Loading indicator disappeared after {:.1f} seconds", waited)
                                elif loading_detected:
                                    logger.info("✓ Loading complete (no indicator found) after {:.1f} seconds", waited)
                                # Even if no loading indicator, wait a bit more to ensure content is loaded
                                if waited < 1.0:  # Wait at least 1 second
                                    time.sleep(check_interval)
                                    waited += check_interval
                                else:
                                    break
                            
                            if waited % 1 == 0 and waited > 0:
                                logger.info("  Still waiting... ({:.1f}/{}s)", waited, max_wait)
                        
                        if waited >= max_wait:
                            logger.info("⚠ Max wait time reached ({}s). Checking if content loaded anyway...", max_wait)
                        
                        # Wait for DOM to settle
                        logger.info("Waiting for DOM to settle...")
                        time.sleep(1)
                        
                        # Try to wait for network idle (with shorter timeout)
                        try:
                            logger.info("Waiting for network to be idle...")
                            scraper.page.wait_for_load_state("networkidle", timeout=5000)
                            logger.info("✓ Network idle")
                        except Exception:
                            logger.debug("Network idle timeout (this is usually fine)")
                        
                        # Final wait for any animations/transitions
                        time.sleep(0.5)
                        
                        # Get updated HTML and count new cards
                        html = scraper.get_html()
                        soup = BeautifulSoup(html, "html.parser")
                        new_cards = soup.select(".row.shadow-card")
                        cards_after = len(new_cards)
                        
                        logger.info("Cards after click: {}", cards_after)
                        new_cards_count = cards_after - cards_before
                        
                        if new_cards_count > 0:
                            logger.info("✓ SUCCESS: {} new cards loaded! (Total: {})", new_cards_count, cards_after)
                            cards = new_cards
                            clicks += 1
                        else:
                            logger.info("⚠ No new cards loaded. Load More may be exhausted or failed.")
                            # Check if button still exists
                            if scraper.page.query_selector("#loadMore"):
                                logger.info("  Button still exists, but no new content. Stopping.")
                            break
                        
                        logger.info("=" * 60)
                        
                    except Exception as exc:  # noqa: BLE001
                        logger.error("✗ Error clicking Load More on {}: {}", hospital_url, exc)
                        logger.exception("Full error details:")
                        break
                
                final_card_count = len(cards)
                total_loaded = final_card_count - initial_card_count
                logger.info("Load More process complete: {} clicks, {} total cards loaded ({} new)", 
                           clicks, final_card_count, total_loaded)

        except Exception:
            # If Playwright interactions are not possible for some reason, fall back to initial cards
            logger.debug("Could not interact with Load More button for {} — proceeding with initial cards", hospital_url)

        return cards

