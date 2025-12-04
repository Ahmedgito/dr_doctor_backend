"""Refactored Marham scraper using modular components."""

from __future__ import annotations

from typing import Dict, List, Optional
import time

from scrapers.base_scraper import BaseScraper
from scrapers.database.mongo_client import MongoClientManager
from scrapers.models.doctor_model import DoctorModel
from scrapers.models.hospital_model import HospitalModel
from scrapers.logger import logger

from scrapers.marham.parsers.hospital_parser import HospitalParser
from scrapers.marham.parsers.doctor_parser import DoctorParser
from scrapers.marham.enrichers.profile_enricher import ProfileEnricher
from scrapers.marham.collectors.doctor_collector import DoctorCollector
from scrapers.marham.mergers.data_merger import DataMerger
from scrapers.marham.handlers.hospital_practice_handler import HospitalPracticeHandler


BASE_URL = "https://www.marham.pk"
HOSPITALS_LISTING = f"{BASE_URL}/hospitals/karachi?page="


class MarhamScraper(BaseScraper):
    """Hospital-first Marham scraper using modular components.

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
        
        # Initialize modular components
        self.hospital_parser = HospitalParser()
        self.doctor_parser = DoctorParser()
        self.profile_enricher = ProfileEnricher()
        self.doctor_collector = DoctorCollector()
        self.data_merger = DataMerger()
        self.practice_handler = HospitalPracticeHandler(mongo_client)

    def _process_doctor(
        self,
        doctor: DoctorModel,
        enriched_hospital: dict,
        hosp_url: str,
        seen_doctor_urls: set,
        stats: Dict[str, int],
    ) -> None:
        """Process a single doctor: enrich, merge, and save.
        
        Args:
            doctor: DoctorModel instance to process
            enriched_hospital: Enriched hospital data dictionary
            hosp_url: Hospital URL
            seen_doctor_urls: Set of doctor URLs already processed in this run
            stats: Statistics dictionary to update
        """
        # Skip if we've already seen this doctor URL in this run
        if doctor.profile_url in seen_doctor_urls:
            logger.info("Skipping duplicate doctor in this run: {}", doctor.profile_url)
            stats["skipped"] += 1
            return

        seen_doctor_urls.add(doctor.profile_url)

        # Attach hospital affiliation
        affiliation = {"name": enriched_hospital.get("name", ""), "url": hosp_url}
        if not doctor.hospitals:
            doctor.hospitals = []
        # Avoid duplicate affiliations
        existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
        if hosp_url not in existing_urls:
            doctor.hospitals.append(affiliation)
        doctor.hospital = enriched_hospital.get("name", "")

        # Enrich doctor from profile page
        try:
            if doctor.profile_url:
                self.load_page(doctor.profile_url)
                self.wait_for("body")
                doc_html = self.get_html()
                details = self.profile_enricher.parse_doctor_profile(doc_html)
                
                # Update doctor model with enriched data
                if details.get("specialties"):
                    doctor.specialty = details.get("specialties")
                if details.get("pmdc_verified"):
                    doctor.pmdc_verified = True
                if details.get("qualifications"):
                    doctor.qualifications = details.get("qualifications")
                if details.get("experience_years"):
                    doctor.experience_years = details.get("experience_years")
                if details.get("work_history"):
                    doctor.work_history = details.get("work_history")
                if details.get("services"):
                    doctor.services = details.get("services")
                if details.get("diseases"):
                    doctor.diseases = details.get("diseases")
                if details.get("symptoms"):
                    doctor.symptoms = details.get("symptoms")
                if details.get("professional_statement"):
                    doctor.professional_statement = details.get("professional_statement")
                if details.get("patients_treated"):
                    doctor.patients_treated = details.get("patients_treated")
                if details.get("reviews_count"):
                    doctor.reviews_count = details.get("reviews_count")
                if details.get("patient_satisfaction_score"):
                    doctor.patient_satisfaction_score = details.get("patient_satisfaction_score")
                if details.get("phone"):
                    doctor.phone = details.get("phone")
                if details.get("consultation_types"):
                    doctor.consultation_types = details.get("consultation_types")
                
                # Process practices: upsert hospital records and attach to doctor.hospitals
                for practice in details.get("practices", []):
                    try:
                        # Add hospital-affiliation info to doctor.hospitals
                        hosp_entry = {
                            "name": practice.get("hospital_name"),
                            "url": practice.get("hospital_url"),
                            "fee": practice.get("fee"),
                            "timings": practice.get("timings"),
                            "practice_id": practice.get("h_id"),
                        }
                        # Avoid duplicates by url
                        existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                        if practice.get("hospital_url") and practice.get("hospital_url") not in existing_urls:
                            doctor.hospitals.append(hosp_entry)

                        # Upsert hospital and add doctor entry into hospital.doctors
                        self.practice_handler.upsert_hospital_practice(practice, doctor)
                    except Exception:
                        continue
        except Exception:
            logger.debug("Could not load or parse doctor profile: {}", doctor.profile_url)

        # Upsert doctor with merge
        if self.mongo_client.doctor_exists(doctor.profile_url):
            existing_doctor = self.mongo_client.doctors.find_one({"profile_url": doctor.profile_url})
            merged = self.data_merger.merge_doctor_records(existing_doctor, doctor)
            if merged:
                try:
                    self.mongo_client.doctors.update_one({"profile_url": doctor.profile_url}, {"$set": merged})
                    stats["updated"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to update doctor {}: {}", doctor.profile_url, exc)
            else:
                stats["skipped"] += 1
        else:
            try:
                self.mongo_client.insert_doctor(doctor.dict())
                stats["inserted"] += 1
                stats["doctors"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to insert doctor {}: {}", doctor.profile_url, exc)

    def scrape(self, limit: Optional[int] = None) -> Dict[str, int]:
        """Scrape hospitals first, then doctors inside each hospital.

        `limit` limits number of hospitals to process (useful for testing).
        Returns stats dict similar to other scrapers.
        """
        logger.info("Starting Marham hospital-first scraping from {}", self.hospitals_listing_url)

        hospital_urls: List[str] = []
        stats = {"total": 0, "inserted": 0, "skipped": 0, "hospitals": 0, "updated": 0, "doctors": 0}

        # Track URLs seen in this run to skip duplicates within the same scrape session
        seen_hospital_urls: set = set()
        seen_doctor_urls: set = set()

        # ---------------- Phase 1: Collect minimal hospital entries (name + url)
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

            hospitals = self.hospital_parser.parse_hospital_cards(html)
            if not hospitals:
                break

            for h in hospitals:
                if not h.get("name"):
                    continue

                # Insert a minimal hospital record (name + url). We'll enrich it later.
                try:
                    exists = False
                    if hasattr(self.mongo_client, "hospital_exists"):
                        exists = self.mongo_client.hospital_exists(h.get("name"), h.get("address"))
                    else:
                        exists = self.mongo_client.hospitals.find_one({"name": h.get("name"), "address": h.get("address")}) is not None

                    if not exists:
                        # minimal doc: use update_hospital (upsert) when available to avoid unique index errors
                        minimal = {"name": h.get("name"), "platform": self.PLATFORM, "url": h.get("url")}
                        if hasattr(self.mongo_client, "update_hospital"):
                            ok = self.mongo_client.update_hospital(h.get("url"), minimal)
                            if ok:
                                stats["hospitals"] += 1
                        else:
                            try:
                                self.mongo_client.insert_hospital(HospitalModel(**minimal).dict())
                                stats["hospitals"] += 1
                            except Exception as exc:
                                logger.debug("Insert minimal hospital exception for {}: {}", h.get("name"), exc)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not insert minimal hospital {}: {}", h.get("name"), exc)

                if h.get("url"):
                    hospital_urls.append(h.get("url"))
                    seen_hospital_urls.add(h.get("url"))

                if limit and len(hospital_urls) >= limit:
                    break

            if limit and len(hospital_urls) >= limit:
                break

            page += 1
            time.sleep(0.5)

        logger.info("Collected {} hospital URLs to process", len(hospital_urls))

        # ---------------- Phase 2: Enrich hospitals then collect & save doctors
        for hosp_url in hospital_urls:
            try:
                # Load hospital page and enrich hospital doc
                self.load_page(hosp_url)
                self.wait_for("body")
                hosp_html = self.get_html()
                enriched = self.hospital_parser.parse_full_hospital(hosp_html, hosp_url)

                # Check if hospital data has changed before updating
                existing_hospital = self.mongo_client.hospitals.find_one({"url": hosp_url})
                if existing_hospital:
                    # Compare relevant fields (ignore _id and scraped_at for comparison)
                    existing_data = {k: v for k, v in existing_hospital.items() if k not in ("_id", "scraped_at")}
                    enriched_data = {k: v for k, v in enriched.items() if k not in ("_id", "scraped_at")}

                    if existing_data == enriched_data:
                        logger.info("Hospital data unchanged for {}: skipping update", hosp_url)
                    else:
                        logger.info("Hospital data changed for {}: updating", hosp_url)
                        try:
                            if hasattr(self.mongo_client, "update_hospital"):
                                self.mongo_client.update_hospital(hosp_url, enriched)
                                stats["updated"] += 1
                        except Exception:
                            logger.warning("Failed to update hospital {}", hosp_url)
                else:
                    # New hospital, insert it
                    logger.info("New hospital found: {}", hosp_url)
                    try:
                        if hasattr(self.mongo_client, "update_hospital"):
                            self.mongo_client.update_hospital(hosp_url, enriched)
                            stats["hospitals"] += 1
                    except Exception:
                        logger.warning("Failed to insert hospital {}", hosp_url)

                # Collect doctor cards and save doctors
                cards = self.doctor_collector.collect_doctor_cards_from_hospital(self, hosp_url)
                for card in cards:
                    stats["total"] += 1

                    doctor = self.doctor_parser.parse_doctor_card(card, hosp_url)
                    if not doctor:
                        stats["skipped"] += 1
                        continue

                    self._process_doctor(doctor, enriched, hosp_url, seen_doctor_urls, stats)

                # Also extract and save doctors from the About section doctor list
                doctors_from_list = self.doctor_parser.extract_doctors_from_list(hosp_html, hosp_url)
                for doctor_info in doctors_from_list:
                    stats["total"] += 1

                    profile_url = doctor_info["profile_url"]

                    # Create minimal DoctorModel from list entry (name + URL only)
                    doctor = DoctorModel(
                        name=doctor_info["name"],
                        specialty=[],
                        fees=None,
                        city="Karachi",
                        area="",
                        hospital=None,
                        hospitals=[],
                        address=enriched.get("address", ""),
                        rating=None,
                        experience="",
                        profile_url=profile_url,
                        platform=self.PLATFORM,
                    )

                    self._process_doctor(doctor, enriched, hosp_url, seen_doctor_urls, stats)

            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed processing hospital {}: {}", hosp_url, exc)

            # polite pause between hospitals
            time.sleep(1)

        logger.info("Marham scraping finished: {}", stats)
        return stats

