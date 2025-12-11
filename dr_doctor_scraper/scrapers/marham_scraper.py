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
from scrapers.marham.collectors.city_collector import CityCollector
from scrapers.marham.mergers.data_merger import DataMerger
from scrapers.marham.handlers.hospital_practice_handler import HospitalPracticeHandler
from scrapers.utils.url_parser import is_hospital_url, parse_hospital_url

BASE_URL = "https://www.marham.pk"
HOSPITALS_LISTING = f"{BASE_URL}/hospitals/karachi?page="


class MarhamScraper(BaseScraper):
    """Hospital-first Marham scraper using modular components.

    Two-Phase Workflow:
    Phase 1: Hospital Collection
    - Paginate hospital listing pages
    - Visit each hospital URL and collect comprehensive hospital data
    - Extract all doctor names and URLs from hospital pages
    - Store minimal doctor info in hospital.doctors (name + profile_url)
    
    Phase 2: Doctor Processing
    - Process all collected doctor URLs
    - Enrich doctor profiles (qualifications, services, etc.)
    - Separate hospitals from private practices (video consultations)
    - Update hospital.doctors with full doctor info (fee, timings)
    - Update doctor.hospitals with hospital affiliations

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
        disable_js: bool = False,
    ) -> None:
        super().__init__(headless=headless, timeout_ms=timeout_ms, max_retries=max_retries, disable_js=disable_js)
        self.mongo_client = mongo_client
        self.hospitals_listing_url = hospitals_listing_url
        
        # Initialize modular components
        self.hospital_parser = HospitalParser()
        self.doctor_parser = DoctorParser()
        self.profile_enricher = ProfileEnricher()
        self.doctor_collector = DoctorCollector()
        self.city_collector = CityCollector()
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

        # Attach hospital affiliation (only if it's a real hospital URL)
        if is_hospital_url(hosp_url):
            affiliation = {"name": enriched_hospital.get("name", ""), "url": hosp_url}
            if not doctor.hospitals:
                doctor.hospitals = []
            # Avoid duplicate affiliations
            existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
            if hosp_url not in existing_urls:
                doctor.hospitals.append(affiliation)

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
                
                # Process practices: separate hospitals from private practice
                for practice in details.get("practices", []):
                    try:
                        practice_url = practice.get("hospital_url")
                        is_private = practice.get("is_private_practice", False)
                        
                        if is_private or not is_hospital_url(practice_url):
                            # This is a private practice (video consultation, home visit, etc.)
                            if not doctor.private_practice:
                                doctor.private_practice = {
                                    "name": practice.get("hospital_name") or f"{doctor.name}'s Private Practice",
                                    "url": practice_url,
                                    "fee": practice.get("fee"),
                                    "timings": practice.get("timings"),
                                }
                        else:
                            # This is a real hospital - add to doctor.hospitals
                            if not doctor.hospitals:
                                doctor.hospitals = []
                            
                            hosp_entry = {
                                "name": practice.get("hospital_name"),
                                "url": practice_url,
                                "fee": practice.get("fee"),
                                "timings": practice.get("timings"),
                                "practice_id": practice.get("h_id"),
                            }
                            # Avoid duplicates by url
                            existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                            if practice_url and practice_url not in existing_urls:
                                doctor.hospitals.append(hosp_entry)

                            # Upsert hospital and add doctor entry into hospital.doctors
                            self.practice_handler.upsert_hospital_practice(practice, doctor)
                    except Exception:
                        continue
        except Exception:
            logger.debug("Could not load or parse doctor profile: {}", doctor.profile_url)

        # Upsert doctor with merge (prevents data leaks - preserves existing data)
        existing_doctor = self.mongo_client.doctors.find_one({"profile_url": doctor.profile_url})
        
        if existing_doctor:
            # Merge existing data with new data (preserves existing fields, prevents data leaks)
            merged = self.data_merger.merge_doctor_records(existing_doctor, doctor)
            if merged:
                try:
                    # Update with merged data and set status to "processed"
                    # Use $set to only update specified fields (prevents data leaks)
                    self.mongo_client.doctors.update_one(
                        {"profile_url": doctor.profile_url},
                        {"$set": {**merged, "scrape_status": "processed"}}
                    )
                    # Also update status separately to ensure it's set
                    self.mongo_client.update_doctor_status(doctor.profile_url, "processed")
                    stats["updated"] += 1
                    stats["doctors"] += 1
                    logger.debug("Updated doctor: {} (status: processed)", doctor.profile_url)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to update doctor {}: {}", doctor.profile_url, exc)
                    stats["errors"] = stats.get("errors", 0) + 1
            else:
                # No changes needed, but ensure status is updated
                self.mongo_client.update_doctor_status(doctor.profile_url, "processed")
                stats["skipped"] += 1
                stats["doctors"] += 1
                logger.debug("Skipped doctor (no changes): {} (status: processed)", doctor.profile_url)
        else:
            # New doctor - insert with status "processed"
            try:
                doctor_dict = doctor.dict()
                doctor_dict["scrape_status"] = "processed"
                # Use insert_doctor which now uses upsert to prevent duplicates
                self.mongo_client.insert_doctor(doctor_dict)
                # Ensure status is set
                self.mongo_client.update_doctor_status(doctor.profile_url, "processed")
                stats["inserted"] += 1
                stats["doctors"] += 1
                logger.debug("Inserted new doctor: {} (status: processed)", doctor.profile_url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to insert doctor {}: {}", doctor.profile_url, exc)
                stats["errors"] = stats.get("errors", 0) + 1

    def scrape(self, limit: Optional[int] = None, step: Optional[int] = None) -> Dict[str, int]:
        """Resumable scraping workflow with four steps:
        
        Step 0: Collect all cities from hospitals page → save to cities collection with status="pending"
        Step 1: Collect hospitals from listing pages (per city) → save to DB with status="pending"
        Step 2: Read hospitals from DB → enrich data → collect doctor URLs → save to DB → update status="doctors_collected"
        Step 3: Read doctors from DB → process profiles → update status="processed"
        
        `limit` limits number of hospitals to process in Step 2 (useful for testing).
        `step` allows running only a specific step (0, 1, 2, or 3). None = run all steps.
        Returns stats dict similar to other scrapers.
        """
        logger.info("Starting resumable Marham scraping workflow")
        stats = {"total": 0, "inserted": 0, "skipped": 0, "hospitals": 0, "updated": 0, "doctors": 0, "cities": 0}

        if step is None or step == 0:
            # Step 0: Collect cities
            self._step0_collect_cities(stats)
        
        if step is None or step == 1:
            # Step 1: Collect hospitals from listing pages
            self._step1_collect_hospitals_from_listings(limit, stats)
        
        if step is None or step == 2:
            # Step 2: Enrich hospitals and collect doctor URLs
            self._step2_enrich_hospitals_and_collect_doctors(limit, stats)
        
        if step is None or step == 3:
            # Step 3: Process all collected doctors
            self._step3_process_doctors(stats)
        
        return stats

    def _step0_collect_cities(self, stats: Dict[str, int]) -> None:
        """Step 0: Collect all cities from the hospitals page and save to cities collection."""
        logger.info("Step 0: Collecting cities from hospitals page")
        
        cities = self.city_collector.collect_cities()
        
        for city_data in cities:
            name = city_data.get("name")
            url = city_data.get("url")
            
            if not name or not url:
                continue
            
            # Check if city already exists
            if self.mongo_client.city_exists(url):
                logger.debug("City already in DB: {}", url)
                stats["skipped"] += 1
                continue
            
            # Upsert city
            if self.mongo_client.upsert_city(name, url):
                stats["cities"] += 1
                logger.info("Saved city to DB: {} -> {}", name, url)
            else:
                logger.warning("Failed to save city: {} -> {}", name, url)
        
        logger.info("Step 0 completed: {} cities collected, {} skipped", stats["cities"], stats["skipped"])

    def _step1_collect_hospitals_from_listings(self, limit: Optional[int], stats: Dict[str, int]) -> None:
        """Step 1: Collect hospitals from listing pages (per city) and save to DB with status='pending'."""
        logger.info("Step 1: Collecting hospitals from listing pages")
        
        # Get all cities that need scraping
        cities_cursor = self.mongo_client.get_cities_needing_scraping()
        cities = list(cities_cursor)
        
        if not cities:
            logger.warning("No cities found in database. Run Step 0 first to collect cities.")
            return
        
        logger.info("Processing hospitals for {} cities", len(cities))
        
        total_collected = 0
        
        for city_doc in cities:
            city_name = city_doc.get("name", "Unknown")
            city_url = city_doc.get("url")
            
            if not city_url:
                continue
            
            logger.info("Processing hospitals for city: {} ({})", city_name, city_url)
            
            # Extract city slug from URL for pagination
            # URL format: https://www.marham.pk/hospitals/{city} or https://www.marham.pk/hospitals/{city}?page=x
            # We need to strip any existing query parameters to build clean pagination URLs
            if "/hospitals/" in city_url:
                # Extract the city slug, removing any query parameters
                city_slug = city_url.split("/hospitals/")[-1].split("?")[0].strip()
                if not city_slug:
                    logger.warning("Empty city slug extracted from URL: {}", city_url)
                    continue
            else:
                logger.warning("Invalid city URL format (missing /hospitals/): {}", city_url)
                continue
            
            page = 1
            city_collected = 0
            
            while True:
                # Build clean URL for this city and page
                # Format: https://www.marham.pk/hospitals/{city_slug}?page={page}
                url = f"{BASE_URL}/hospitals/{city_slug}?page={page}"
                logger.debug("Loading hospitals page {} for city {}: {}", page, city_name, url)
                
                try:
                    self.load_page(url)
                    self.wait_for("body")
                    html = self.get_html()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to load hospitals page {}: {}", url, exc)
                    break

                hospitals = self.hospital_parser.parse_hospital_cards(html)
                if not hospitals:
                    logger.info("No more hospitals found on page {} for city {}, stopping", page, city_name)
                    break

                for h in hospitals:
                    if not h.get("name") or not h.get("url"):
                        continue

                    hospital_url = h.get("url")
                    
                    # Check if hospital already exists in DB by URL (unique identifier)
                    existing = self.mongo_client.hospitals.find_one({"url": hospital_url})
                    if existing:
                        logger.debug("Hospital already in DB (skipping duplicate): {} ({})", h.get("name"), hospital_url)
                        city_collected += 1
                        continue

                    # Extract location from "View Directions" button
                    if self.page:
                        try:
                            location = self.hospital_parser.extract_location_from_card(self.page, h["url"])
                            if location:
                                h["location"] = location
                                logger.debug("Extracted location for {}: {}", h.get("name"), location)
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("Failed to extract location for {}: {}", h.get("name"), exc)

                    # Save minimal hospital record to DB with status="pending"
                    try:
                        minimal = {
                            "name": h.get("name"),
                            "platform": self.PLATFORM,
                            "url": h.get("url"),
                            "address": h.get("address"),
                            "city": h.get("city") or city_name,  # Use city from city collection if not in hospital data
                            "area": h.get("area"),
                            "scrape_status": "pending"
                        }
                        if h.get("location"):
                            minimal["location"] = h["location"]
                        
                        if self.mongo_client.update_hospital(h.get("url"), minimal):
                            stats["hospitals"] += 1
                            city_collected += 1
                            logger.info("Saved hospital to DB: {} ({})", h.get("name"), h.get("url"))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Failed to save hospital {}: {}", h.get("name"), exc)

                    if limit and total_collected + city_collected >= limit:
                        break

                if limit and total_collected + city_collected >= limit:
                    break

                page += 1
                time.sleep(0.5)
            
            # Mark city as scraped if we collected hospitals
            if city_collected > 0:
                self.mongo_client.update_city_status(city_url, "scraped")
                logger.info("Marked city {} as scraped ({} hospitals collected)", city_name, city_collected)
            
            total_collected += city_collected
            
            if limit and total_collected >= limit:
                break
        
        logger.info("Step 1 completed: {} hospitals collected across all cities", total_collected)

    def _step2_enrich_hospitals_and_collect_doctors(self, limit: Optional[int], stats: Dict[str, int]) -> None:
        """Step 2: Read hospitals from DB, enrich them, collect doctor URLs, and save to DB."""
        logger.info("Step 2: Enriching hospitals and collecting doctor URLs")
        
        # Get hospitals that need enrichment/doctor collection
        hospitals_cursor = self.mongo_client.get_hospitals_needing_doctor_collection(limit=limit)
        hospitals_to_process = list(hospitals_cursor)
        
        logger.info("Found {} hospitals needing enrichment/doctor collection", len(hospitals_to_process))
        
        for hospital_doc in hospitals_to_process:
            hosp_url = hospital_doc.get("url")
            if not hosp_url:
                continue
            try:
                logger.info("Processing hospital: {} ({})", hospital_doc.get("name"), hosp_url)
                
                # Load hospital page and enrich hospital doc
                self.load_page(hosp_url)
                self.wait_for("body")
                hosp_html = self.get_html()
                enriched = self.hospital_parser.parse_full_hospital(hosp_html, hosp_url)

                # Preserve location from existing record if enriched data doesn't have it
                if hospital_doc.get("location") and not enriched.get("location"):
                    enriched["location"] = hospital_doc["location"]

                # Update hospital with enriched data
                enriched["scrape_status"] = "enriched"  # Will be updated to "doctors_collected" after collecting doctors
                try:
                    if self.mongo_client.update_hospital(hosp_url, enriched):
                        stats["updated"] += 1
                        logger.info("Enriched hospital: {}", hosp_url)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to update hospital {}: {}", hosp_url, exc)
                    continue

                # Collect doctor names and URLs from hospital page
                cards = self.doctor_collector.collect_doctor_cards_from_hospital(self, hosp_url)
                hospital_doctors_list = []
                seen_doctor_urls_in_hosp = set()
                
                # Collect from doctor cards
                for card in cards:
                    doctor = self.doctor_parser.parse_doctor_card(card, hosp_url)
                    if doctor and doctor.profile_url and doctor.profile_url not in seen_doctor_urls_in_hosp:
                        hospital_doctors_list.append({
                            "name": doctor.name,
                            "profile_url": doctor.profile_url,
                        })
                        seen_doctor_urls_in_hosp.add(doctor.profile_url)
                        
                        # Save minimal doctor record to DB for later processing
                        self.mongo_client.upsert_minimal_doctor(doctor.profile_url, doctor.name, hosp_url)

                # Also extract doctors from the About section doctor list
                doctors_from_list = self.doctor_parser.extract_doctors_from_list(hosp_html, hosp_url)
                for doctor_info in doctors_from_list:
                    profile_url = doctor_info["profile_url"]
                    if profile_url and profile_url not in seen_doctor_urls_in_hosp:
                        hospital_doctors_list.append({
                            "name": doctor_info["name"],
                            "profile_url": profile_url,
                        })
                        seen_doctor_urls_in_hosp.add(profile_url)
                        
                        # Save minimal doctor record to DB
                        self.mongo_client.upsert_minimal_doctor(profile_url, doctor_info["name"], hosp_url)
                
                # Also get doctors from enriched data (from About section parser)
                if enriched.get("doctors"):
                    for doc_info in enriched.get("doctors", []):
                        profile_url = doc_info.get("profile_url")
                        if profile_url and profile_url not in seen_doctor_urls_in_hosp:
                            hospital_doctors_list.append(doc_info)
                            seen_doctor_urls_in_hosp.add(profile_url)
                            
                            # Save minimal doctor record to DB
                            self.mongo_client.upsert_minimal_doctor(profile_url, doc_info.get("name", ""), hosp_url)
                
                # Update hospital with doctor list and mark as "doctors_collected"
                try:
                    # Merge with existing doctors list
                    existing_hosp = self.mongo_client.hospitals.find_one({"url": hosp_url})
                    existing_doctors = existing_hosp.get("doctors", []) if existing_hosp else []
                    
                    # Create a map of existing doctors by profile_url
                    existing_map = {d.get("profile_url"): d for d in existing_doctors if isinstance(d, dict) and d.get("profile_url")}
                    
                    # Merge new doctors
                    for new_doc in hospital_doctors_list:
                        profile_url = new_doc.get("profile_url")
                        if profile_url and profile_url not in existing_map:
                            existing_doctors.append(new_doc)
                    
                    # Update hospital with doctors list and status
                    self.mongo_client.hospitals.update_one(
                        {"url": hosp_url},
                        {"$set": {"doctors": existing_doctors, "scrape_status": "doctors_collected"}},
                        upsert=True
                    )
                    logger.info("Updated hospital {} with {} doctors, status set to 'doctors_collected'", hosp_url, len(existing_doctors))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to update hospital doctors list for {}: {}", hosp_url, exc)

            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed processing hospital {}: {}", hosp_url, exc)

            # polite pause between hospitals
            time.sleep(1)

        logger.info("Step 2 complete: Hospitals enriched and doctor URLs collected")

    def _step3_process_doctors(self, stats: Dict[str, int]) -> None:
        """Step 3: Read doctors from DB and process their profiles."""
        logger.info("Step 3: Processing doctors from DB")
        
        # Get doctors that need processing
        doctors_cursor = self.mongo_client.get_doctors_needing_processing()
        doctors_to_process = list(doctors_cursor)
        
        logger.info("Found {} doctors needing processing", len(doctors_to_process))

        for doctor_doc in doctors_to_process:
            try:
                profile_url = doctor_doc.get("profile_url")
                if not profile_url:
                    continue
                    
                stats["total"] += 1
                logger.info("Processing doctor: {} ({})", doctor_doc.get("name"), profile_url)

                # Load doctor profile page
                self.load_page(profile_url)
                self.wait_for("body")
                doc_html = self.get_html()
                details = self.profile_enricher.parse_doctor_profile(doc_html)

                # Create or update doctor model from existing doc
                # Filter out MongoDB-specific fields and ensure all required fields are present
                doctor_data = {k: v for k, v in doctor_doc.items() if k != "_id"}
                # Ensure specialty is a list (it might be missing or empty)
                if "specialty" not in doctor_data or not doctor_data["specialty"]:
                    doctor_data["specialty"] = []
                doctor = DoctorModel(**doctor_data)

                # Update doctor with enriched data
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

                # Process practices: separate hospitals from private practice
                if not doctor.hospitals:
                    doctor.hospitals = []
                
                for practice in details.get("practices", []):
                    try:
                        is_private = practice.get("is_private_practice", False)
                        practice_url = practice.get("practice_url")  # Booking/appointment URL
                        hospital_url = practice.get("hospital_url")  # Hospital URL (if it's a hospital)
                        
                        if is_private:
                            # Private practice (video consultation, etc.)
                            # Use practice_url (the booking URL) for private practice
                            if not doctor.private_practice:
                                doctor.private_practice = {
                                    "name": practice.get("hospital_name") or f"{doctor.name}'s Private Practice",
                                    "url": practice_url,  # Use the booking/consultation URL
                                    "fee": practice.get("fee"),
                                    "timings": practice.get("timings"),
                                }
                        else:
                            # Real hospital - add to doctor.hospitals
                            # For hospitals, we need to construct or find the actual hospital URL
                            # The practice_url might be a callcenter link, but we need the hospital page URL
                            # For now, use hospital_url if available, otherwise try to construct from practice_url
                            hosp_url = hospital_url
                            if not hosp_url and practice_url:
                                # Try to extract hospital info from practice_url
                                # If practice_url contains hospital info, we can use it
                                # Otherwise, we'll need to look it up
                                if is_hospital_url(practice_url):
                                    hosp_url = practice_url
                            
                            if hosp_url:
                                hosp_entry = {
                                    "name": practice.get("hospital_name"),
                                    "url": hosp_url,
                                    "fee": practice.get("fee"),
                                    "timings": practice.get("timings"),
                                    "practice_id": practice.get("h_id"),
                                    "area": practice.get("area"),
                                }
                                # Add location if available
                                if practice.get("lat") and practice.get("lng"):
                                    hosp_entry["location"] = {
                                        "lat": practice.get("lat"),
                                        "lng": practice.get("lng"),
                                    }
                                
                                # Avoid duplicates by url
                                existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                                if hosp_url not in existing_urls:
                                    doctor.hospitals.append(hosp_entry)

                                # Update hospital.doctors with this doctor's info and save hospital with location
                                # Make sure practice dict has hospital_url set for the handler
                                practice["hospital_url"] = hosp_url
                                self.practice_handler.upsert_hospital_practice(practice, doctor)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Error processing practice: {}", exc)
                        continue

                # Also add hospitals from hospitals collection where this doctor is listed
                # Find hospitals that have this doctor in their doctors list
                hospitals_with_doctor = self.mongo_client.hospitals.find({
                    "doctors.profile_url": profile_url
                })
                
                for hosp_doc in hospitals_with_doctor:
                    hosp_url = hosp_doc.get("url")
                    if hosp_url and is_hospital_url(hosp_url):
                        existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                        if hosp_url not in existing_urls:
                            doctor.hospitals.append({
                                "name": hosp_doc.get("name", ""),
                                "url": hosp_url,
                            })

                # Save doctor with updated status
                doctor_dict = doctor.dict()
                doctor_dict["scrape_status"] = "processed"
                
                try:
                    self.mongo_client.doctors.update_one(
                        {"profile_url": profile_url},
                        {"$set": doctor_dict}
                    )
                    stats["updated"] += 1
                    stats["doctors"] += 1
                    logger.info("Processed and saved doctor: {}", profile_url)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to update doctor {}: {}", profile_url, exc)
                    stats["skipped"] += 1

            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed processing doctor {}: {}", doctor_doc.get("profile_url"), exc)
                stats["skipped"] += 1

            # polite pause between doctors
            time.sleep(0.5)

        logger.info("Step 3 complete: {} doctors processed", len(doctors_to_process))

