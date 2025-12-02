from __future__ import annotations

from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.database.mongo_client import MongoClientManager
from scrapers.models.doctor_model import DoctorModel
from scrapers.utils.parser_helpers import clean_text, extract_number, normalize_fee
from scrapers.logger import logger


class OladocScraper(BaseScraper):
    """Scraper for Oladoc doctor profiles.

    This is a template with generic selectors; adjust selectors as needed
    based on the latest Oladoc HTML structure.
    """

    PLATFORM = "oladoc"

    def __init__(
        self,
        mongo_client: MongoClientManager,
        listing_url: str = "https://www.oladoc.com/doctors",
        headless: bool = True,
        timeout_ms: int = 15000,
        max_retries: int = 3,
    ) -> None:
        super().__init__(headless=headless, timeout_ms=timeout_ms, max_retries=max_retries)
        self.mongo_client = mongo_client
        self.listing_url = listing_url

    # ---------------------------------------------------------------------

    def _extract_profile_links(self, html: str) -> List[str]:
        """Extract profile URLs from listing page HTML."""

        soup = BeautifulSoup(html, "html.parser")
        links: List[str] = []

        # Example selectors; may need updates over time
        for card in soup.select("a[href*='/doctors/']"):
            href = card.get("href")
            if not href:
                continue
            if href.startswith("/"):
                href = "https://www.oladoc.com" + href
            if href not in links:
                links.append(href)

        logger.info("Found {} Oladoc profile links on listing page", len(links))
        return links

    def _parse_profile(self, html: str, profile_url: str) -> Optional[DoctorModel]:
        """Parse one doctor profile page into a DoctorModel instance."""

        soup = BeautifulSoup(html, "html.parser")

        name = clean_text(self._first_text(soup.select_one("h1")))
        specialties = [
            clean_text(li.get_text())
            for li in soup.select(".speciality, .specialties li, .doctor-specialities li")
            if clean_text(li.get_text())
        ]

        fees_text = clean_text(self._first_text(soup.select_one(".fee, .doctor-fee, .consultation-fee")))
        city = clean_text(self._first_text(soup.select_one(".city, .doctor-city"))) or ""
        area = clean_text(self._first_text(soup.select_one(".area, .doctor-area")))
        hospital = clean_text(self._first_text(soup.select_one(".hospital, .doctor-hospital")))
        address = clean_text(self._first_text(soup.select_one(".address, .clinic-address")))

        rating_text = clean_text(self._first_text(soup.select_one(".rating, .doctor-rating span")))
        experience = clean_text(self._first_text(soup.select_one(".experience, .doctor-experience")))

        if not name:
            logger.warning("Skipping Oladoc profile without name: {}", profile_url)
            return None

        model = DoctorModel(
            name=name,
            specialty=specialties,
            fees=normalize_fee(fees_text),
            city=city,
            area=area,
            hospital=hospital,
            address=address,
            rating=(extract_number(rating_text) if rating_text else None),
            experience=experience,
            profile_url=profile_url,
            platform=self.PLATFORM,
        )
        return model

    @staticmethod
    def _first_text(element) -> Optional[str]:  # noqa: ANN001
        return element.get_text(strip=True) if element else None

    # ------------------------------------------------------------------

    def scrape(self, limit: Optional[int] = None) -> Dict[str, int]:
        """Scrape doctors from Oladoc.

        Returns stats dict: {"total": int, "inserted": int, "skipped": int}
        """

        logger.info("Starting Oladoc scraping from {}", self.listing_url)
        self.load_page(self.listing_url)
        self.wait_for("body")
        listing_html = self.get_html()

        profile_links = self._extract_profile_links(listing_html)
        if limit is not None:
            profile_links = profile_links[:limit]

        total = 0
        inserted = 0
        skipped = 0

        for url in profile_links:
            total += 1
            if self.mongo_client.doctor_exists(url):
                logger.info("Duplicate doctor (already exists) skipped: {}", url)
                skipped += 1
                continue

            logger.info("Scraping Oladoc profile {} of {}: {}", total, len(profile_links), url)
            self.load_page(url)
            self.wait_for("body")
            html = self.get_html()

            try:
                model = self._parse_profile(html, url)
                if not model:
                    skipped += 1
                    continue

                doc_dict = model.dict()
                self.mongo_client.insert_doctor(doc_dict)
                inserted += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Error parsing/saving Oladoc profile {}: {}", url, exc)
                skipped += 1

        logger.info(
            "Oladoc scraping finished. total={}, inserted={}, skipped={}",
            total,
            inserted,
            skipped,
        )
        return {"total": total, "inserted": inserted, "skipped": skipped}
