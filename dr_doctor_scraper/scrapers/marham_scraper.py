from __future__ import annotations

from typing import Dict, List, Optional
import time

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.database.mongo_client import MongoClientManager
from scrapers.models.doctor_model import DoctorModel
from scrapers.models.hospital_model import HospitalModel
from scrapers.utils.parser_helpers import clean_text, extract_number, normalize_fee
from scrapers.logger import logger


BASE_URL = "https://www.marham.pk"
HOSPITALS_LISTING = f"{BASE_URL}/hospitals/karachi?page="


class MarhamScraper(BaseScraper):
    """Hospital-first Marham scraper.

    Workflow:
    - Paginate hospital listing pages and save hospitals to DB.
    - For each hospital page, collect doctor cards (click "Load More" if present).
    - Save doctors to DB using `DoctorModel` and `MongoClientManager`.

    This keeps the same public interface as the previous `MarhamScraper` so
    `run_scraper.py` can use it unchanged.
    """

    PLATFORM = "marham"

    def __init__(
        self,
        mongo_client: MongoClientManager,
        hospitals_listing_url: str = HOSPITALS_LISTING,
        headless: bool = True,
        timeout_ms: int = 15000,
        max_retries: int = 3,
    ) -> None:
        super().__init__(headless=headless, timeout_ms=timeout_ms, max_retries=max_retries)
        self.mongo_client = mongo_client
        self.hospitals_listing_url = hospitals_listing_url

    # ------------------ Hospital listing extraction ------------------
    def _parse_hospital_cards(self, html: str) -> List[dict]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".row.shadow-card")
        hospitals: List[dict] = []

        for card in cards:
            name_tag = card.select_one(".hosp_list_selected_hosp_name, a[href*='/hospitals/']")
            name = clean_text(name_tag.get_text()) if name_tag else None
            href = name_tag.get("href") if name_tag and name_tag.has_attr("href") else None
            url = f"{BASE_URL}{href}" if href and href.startswith("/") else href

            address_p = card.select('p.text-sm')
            address = clean_text(address_p[1].get_text()) if len(address_p) > 1 else clean_text(address_p[0].get_text()) if address_p else None

            hospital = {
                "name": name,
                "city": "Karachi",
                "area": None,
                "address": address,
                "platform": self.PLATFORM,
                "url": url,
            }

            hospitals.append(hospital)

        return hospitals

    # ------------------ Doctor extraction per hospital ------------------
    def _collect_doctor_cards_from_hospital(self, hospital_url: str) -> List[BeautifulSoup]:
        """Load the hospital page and attempt to collect all doctor cards.

        Strategy:
        - Load initial page and gather cards.
        - If a "Load More" button exists, click it repeatedly until it disappears
          or a safety limit is reached.
        - Return list of card elements (BeautifulSoup Tag objects).
        """

        self.load_page(hospital_url)
        self.wait_for("body")
        html = self.get_html()
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".row.shadow-card")

        # If the page uses a client-side "Load More" button, try to click it via Playwright
        try:
            if self.page and self.page.query_selector("#loadMore"):
                logger.info("'Load More' detected on {} — clicking until exhausted", hospital_url)
                clicks = 0
                while clicks < 20 and self.page.query_selector("#loadMore"):
                    try:
                        self.page.click("#loadMore")
                        # give the page a moment to fetch and render new content
                        time.sleep(1)
                        html = self.get_html()
                        soup = BeautifulSoup(html, "html.parser")
                        cards = soup.select(".row.shadow-card")
                        clicks += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Clicking Load More failed on {}: {}", hospital_url, exc)
                        break

        except Exception:
            # If Playwright interactions are not possible for some reason, fall back to initial cards
            logger.debug("Could not interact with Load More button for {} — proceeding with initial cards", hospital_url)

        return cards

    def _parse_doctor_card(self, card, hospital_url: str) -> Optional[DoctorModel]:
        try:
            name_tag = card.select_one("a.dr_profile_opened_from_hospital_profile h3, h3")
            name = clean_text(name_tag.get_text()) if name_tag else None

            parent_a = name_tag.parent if name_tag else None
            profile_href = parent_a.get("href") if parent_a and parent_a.has_attr("href") else None
            profile_url = f"{BASE_URL}{profile_href}" if profile_href and profile_href.startswith("/") else profile_href

            specialty_tag = card.select_one("p.mb-0.text-sm")
            specialty = [clean_text(specialty_tag.get_text())] if specialty_tag and clean_text(specialty_tag.get_text()) else []

            qualifications_tag = card.select_one('p.text-sm:not(.mb-0)')
            qualifications = clean_text(qualifications_tag.get_text()) if qualifications_tag else None

            experience_tag = card.select_one('.row .col-4:nth-child(2) p.text-bold.text-sm')
            experience = clean_text(experience_tag.get_text()) if experience_tag else None

            if not name or not profile_url:
                return None

            model = DoctorModel(
                name=name,
                specialty=specialty,
                fees=None,
                city="Karachi",
                area=None,
                hospital=hospital_url,
                address=None,
                rating=None,
                experience=experience,
                profile_url=profile_url,
                platform=self.PLATFORM,
            )
            return model
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse doctor card on {}: {}", hospital_url, exc)
            return None

    # ------------------ Public scrape method ------------------
    def scrape(self, limit: Optional[int] = None) -> Dict[str, int]:
        """Scrape hospitals first, then doctors inside each hospital.

        `limit` limits number of hospitals to process (useful for testing).
        Returns stats dict similar to other scrapers.
        """

        logger.info("Starting Marham hospital-first scraping from {}", self.hospitals_listing_url)

        hospital_urls: List[str] = []
        stats = {"total": 0, "inserted": 0, "skipped": 0, "hospitals": 0}

        # Paginate hospitals listing
        page = 1
        while True:
            url = f"{self.hospitals_listing_url}{page}"
            logger.debug("Loading hospitals page: {}", url)
            try:
                self.load_page(url)
                self.wait_for("body")
                html = self.get_html()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load hospitals page {}: {}", url, exc)
                break

            hospitals = self._parse_hospital_cards(html)
            if not hospitals:
                break

            for h in hospitals:
                if not h.get("name"):
                    continue
                # insert hospital if missing. Support older/newer MongoClientManager APIs.
                try:
                    if hasattr(self.mongo_client, "hospital_exists"):
                        exists = self.mongo_client.hospital_exists(h.get("name"), h.get("address"))
                    else:
                        exists = self.mongo_client.hospitals.find_one({"name": h.get("name"), "address": h.get("address")}) is not None

                    if not exists:
                        hid = self.mongo_client.insert_hospital(HospitalModel(**h).dict())
                        if hid:
                            stats["hospitals"] += 1
                except Exception:  # noqa: BLE001
                    # If anything goes wrong checking/inserting hospitals, continue gracefully
                    logger.warning("Could not verify/insert hospital: {}", h.get("name"))
                if h.get("url"):
                    hospital_urls.append(h.get("url"))

                if limit and len(hospital_urls) >= limit:
                    break

            if limit and len(hospital_urls) >= limit:
                break

            page += 1
            time.sleep(0.5)

        logger.info("Collected {} hospital URLs to process", len(hospital_urls))

        # For each hospital, collect doctor cards and save doctors
        for hosp_url in hospital_urls:
            cards = self._collect_doctor_cards_from_hospital(hosp_url)
            for card in cards:
                stats["total"] += 1
                doctor = self._parse_doctor_card(card, hosp_url)
                if not doctor:
                    stats["skipped"] += 1
                    continue

                if self.mongo_client.doctor_exists(doctor.profile_url):
                    stats["skipped"] += 1
                    continue

                try:
                    self.mongo_client.insert_doctor(doctor.dict())
                    stats["inserted"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to insert doctor {}: {}", doctor.profile_url, exc)
                    stats["skipped"] += 1

            # polite pause between hospitals
            time.sleep(1)

        logger.info("Marham scraping finished: {}", stats)
        return stats
