"""Multi-threaded wrapper for Marham scraper to speed up data collection."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from queue import Queue

from scrapers.logger import logger
from scrapers.marham_scraper import MarhamScraper
from scrapers.database.mongo_client import MongoClientManager


class MultiThreadedMarhamScraper:
    """Multi-threaded wrapper around MarhamScraper for parallel processing.
    
    This class distributes work across multiple threads:
    - Step 1: Each thread handles different listing pages
    - Step 2: Each thread handles different hospitals
    - Step 3: Each thread handles different doctors
    
    Each thread has its own browser instance to avoid conflicts.
    """
    
    def __init__(
        self,
        mongo_client: MongoClientManager,
        num_threads: int = 4,
        headless: bool = True,
        timeout_ms: int = 15000,
        max_retries: int = 3,
    ) -> None:
        """Initialize multi-threaded scraper.
        
        Args:
            mongo_client: MongoDB client manager (thread-safe)
            num_threads: Number of worker threads (default: 4)
            headless: Run browsers in headless mode
            timeout_ms: Page load timeout in milliseconds
            max_retries: Maximum retries for failed operations
        """
        self.mongo_client = mongo_client
        self.num_threads = num_threads
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        
        # Thread-safe statistics
        self.stats_lock = threading.Lock()
        self.stats = {
            "total": 0,
            "inserted": 0,
            "skipped": 0,
            "hospitals": 0,
            "updated": 0,
            "doctors": 0,
            "errors": 0,
        }
    
    def _update_stats(self, new_stats: Dict[str, int]) -> None:
        """Thread-safe statistics update."""
        with self.stats_lock:
            for key, value in new_stats.items():
                if key in self.stats:
                    self.stats[key] += value
    
    def _step1_worker(self, page_numbers: List[int], limit: Optional[int], num_threads: int) -> Dict[str, int]:
        """Worker thread for Step 1: Collect hospitals from listing pages.
        
        Args:
            page_numbers: List of page numbers to process
            limit: Maximum number of hospitals to collect (None = no limit)
            num_threads: Total number of threads (for limit distribution)
            
        Returns:
            Statistics dictionary
        """
        worker_stats = {"hospitals": 0, "errors": 0}
        thread_id = threading.current_thread().ident
        
        try:
            with MarhamScraper(
                mongo_client=self.mongo_client,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
                max_retries=self.max_retries,
            ) as scraper:
                logger.info(f"[Thread {thread_id}] Starting Step 1 worker for {len(page_numbers)} pages")
                
                for page_num in page_numbers:
                    try:
                        # Check global limit (approximate, since we're in parallel)
                        # Each thread will stop when it reaches its share of the limit
                        thread_limit = (limit // num_threads) + 1 if limit else None
                        if thread_limit and worker_stats["hospitals"] >= thread_limit:
                            logger.info(f"[Thread {thread_id}] Reached thread limit of {thread_limit} hospitals")
                            break
                        
                        # Collect hospitals from this page
                        page_url = f"https://www.marham.pk/hospitals/karachi?page={page_num}"
                        scraper.load_page(page_url)
                        scraper.wait_for("body")
                        html = scraper.get_html()
                        
                        # Parse hospitals from this page
                        hospitals = scraper.hospital_parser.parse_hospital_cards(html)
                        
                        # Save hospitals to database
                        for hospital in hospitals:
                            thread_limit = (limit // num_threads) + 1 if limit else None
                            if thread_limit and worker_stats["hospitals"] >= thread_limit:
                                break
                            
                            try:
                                # Extract location from card if possible
                                location = scraper.hospital_parser.extract_location_from_card(
                                    scraper.page, hospital.get("url", "")
                                )
                                if location:
                                    hospital["location"] = location
                                
                                # Insert minimal hospital record
                                hospital["scrape_status"] = "pending"
                                hospital["platform"] = "marham"
                                
                                if self.mongo_client.insert_hospital(hospital):
                                    worker_stats["hospitals"] += 1
                                    logger.debug(f"[Thread {thread_id}] Collected hospital: {hospital.get('name')}")
                            except Exception as exc:
                                logger.warning(f"[Thread {thread_id}] Failed to insert hospital: {exc}")
                                worker_stats["errors"] += 1
                        
                        logger.info(f"[Thread {thread_id}] Processed page {page_num}: {len(hospitals)} hospitals")
                        
                    except Exception as exc:
                        logger.error(f"[Thread {thread_id}] Error processing page {page_num}: {exc}")
                        worker_stats["errors"] += 1
                        continue
                
                logger.info(f"[Thread {thread_id}] Step 1 worker completed: {worker_stats['hospitals']} hospitals")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Step 1 worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _step2_worker(self, hospital_urls: List[str]) -> Dict[str, int]:
        """Worker thread for Step 2: Enrich hospitals and collect doctors.
        
        Args:
            hospital_urls: List of hospital URLs to process
            
        Returns:
            Statistics dictionary
        """
        worker_stats = {"hospitals": 0, "doctors": 0, "errors": 0}
        thread_id = threading.current_thread().ident
        
        try:
            with MarhamScraper(
                mongo_client=self.mongo_client,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
                max_retries=self.max_retries,
            ) as scraper:
                logger.info(f"[Thread {thread_id}] Starting Step 2 worker for {len(hospital_urls)} hospitals")
                
                for hospital_url in hospital_urls:
                    try:
                        # Load and enrich hospital
                        scraper.load_page(hospital_url)
                        scraper.wait_for("body")
                        html = scraper.get_html()
                        
                        enriched = scraper.hospital_parser.parse_full_hospital(html, hospital_url)
                        enriched["url"] = hospital_url
                        enriched["scrape_status"] = "enriched"
                        
                        # Collect doctors from hospital page
                        doctor_cards = scraper.doctor_collector.collect_doctor_cards_from_hospital(
                            scraper, hospital_url
                        )
                        
                        doctor_urls = []
                        for card in doctor_cards:
                            doctor = scraper.doctor_parser.parse_doctor_card(card, hospital_url)
                            if doctor and doctor.profile_url:
                                doctor_urls.append(doctor.profile_url)
                                
                                # Insert minimal doctor record
                                if self.mongo_client.upsert_minimal_doctor(
                                    profile_url=doctor.profile_url,
                                    name=doctor.name or "",
                                    hospital_url=hospital_url
                                ):
                                    worker_stats["doctors"] += 1
                        
                        # Also extract doctors from About section
                        doctors_from_about = scraper.doctor_parser.extract_doctors_from_list(html, hospital_url)
                        for doc_info in doctors_from_about:
                            if doc_info.get("profile_url"):
                                if self.mongo_client.upsert_minimal_doctor(
                                    profile_url=doc_info["profile_url"],
                                    name=doc_info.get("name", ""),
                                    hospital_url=hospital_url
                                ):
                                    worker_stats["doctors"] += 1
                        
                        # Update hospital in database
                        enriched["scrape_status"] = "doctors_collected"
                        
                        if self.mongo_client.update_hospital(hospital_url, enriched):
                            self.mongo_client.update_hospital_status(hospital_url, "doctors_collected")
                            worker_stats["hospitals"] += 1
                        
                        logger.debug(f"[Thread {thread_id}] Enriched hospital: {enriched.get('name')} ({len(doctor_urls)} doctors)")
                        
                    except Exception as exc:
                        logger.error(f"[Thread {thread_id}] Error processing hospital {hospital_url}: {exc}")
                        worker_stats["errors"] += 1
                        continue
                
                logger.info(f"[Thread {thread_id}] Step 2 worker completed: {worker_stats['hospitals']} hospitals, {worker_stats['doctors']} doctors")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Step 2 worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _step3_worker(self, doctor_urls: List[str]) -> Dict[str, int]:
        """Worker thread for Step 3: Process doctor profiles.
        
        Args:
            doctor_urls: List of doctor profile URLs to process
            
        Returns:
            Statistics dictionary
        """
        worker_stats = {"doctors": 0, "inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        thread_id = threading.current_thread().ident
        
        try:
            with MarhamScraper(
                mongo_client=self.mongo_client,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
                max_retries=self.max_retries,
            ) as scraper:
                logger.info(f"[Thread {thread_id}] Starting Step 3 worker for {len(doctor_urls)} doctors")
                
                for doctor_url in doctor_urls:
                    try:
                        # Get minimal doctor record from database
                        doctor_doc = self.mongo_client.doctors.find_one({"profile_url": doctor_url})
                        if not doctor_doc:
                            logger.warning(f"[Thread {thread_id}] Doctor not found in DB: {doctor_url}")
                            continue
                        
                        # Filter out MongoDB _id field
                        doctor_doc = {k: v for k, v in doctor_doc.items() if k != "_id"}
                        
                        # Create doctor model
                        from scrapers.models.doctor_model import DoctorModel
                        doctor = DoctorModel(**doctor_doc)
                        
                        # Load and enrich doctor profile
                        scraper.load_page(doctor_url)
                        scraper.wait_for("body")
                        html = scraper.get_html()
                        details = scraper.profile_enricher.parse_doctor_profile(html)
                        
                        # Update doctor with enriched data
                        if details.get("specialties"):
                            doctor.specialty = details.get("specialties")
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
                        
                        # Process practices
                        for practice in details.get("practices", []):
                            from scrapers.utils.url_parser import is_hospital_url
                            practice_url = practice.get("hospital_url")
                            is_private = practice.get("is_private_practice", False)
                            
                            if is_private or not is_hospital_url(practice_url):
                                if not doctor.private_practice:
                                    doctor.private_practice = {
                                        "name": practice.get("hospital_name") or f"{doctor.name}'s Private Practice",
                                        "url": practice_url,
                                        "fee": practice.get("fee"),
                                        "timings": practice.get("timings"),
                                    }
                            else:
                                if not doctor.hospitals:
                                    doctor.hospitals = []
                                
                                hosp_entry = {
                                    "name": practice.get("hospital_name"),
                                    "url": practice_url,
                                    "fee": practice.get("fee"),
                                    "timings": practice.get("timings"),
                                    "practice_id": practice.get("h_id"),
                                }
                                
                                existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                                if practice_url and practice_url not in existing_urls:
                                    doctor.hospitals.append(hosp_entry)
                                
                                scraper.practice_handler.upsert_hospital_practice(practice, doctor)
                        
                        # Update doctor in database
                        doctor.scrape_status = "processed"
                        if self.mongo_client.doctor_exists(doctor.profile_url):
                            existing = self.mongo_client.doctors.find_one({"profile_url": doctor.profile_url})
                            merged = scraper.data_merger.merge_doctor_records(existing, doctor)
                            if merged:
                                self.mongo_client.doctors.update_one(
                                    {"profile_url": doctor.profile_url},
                                    {"$set": merged}
                                )
                                worker_stats["updated"] += 1
                            else:
                                worker_stats["skipped"] += 1
                        else:
                            self.mongo_client.insert_doctor(doctor.dict())
                            worker_stats["inserted"] += 1
                        
                        self.mongo_client.update_doctor_status(doctor.profile_url, "processed")
                        worker_stats["doctors"] += 1
                        
                    except Exception as exc:
                        logger.error(f"[Thread {thread_id}] Error processing doctor {doctor_url}: {exc}")
                        worker_stats["errors"] += 1
                        continue
                
                logger.info(f"[Thread {thread_id}] Step 3 worker completed: {worker_stats['doctors']} doctors")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Step 3 worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _distribute_work(self, items: List, num_workers: int) -> List[List]:
        """Distribute items evenly across workers.
        
        Args:
            items: List of items to distribute
            num_workers: Number of workers
            
        Returns:
            List of lists, one per worker
        """
        if not items:
            return []
        
        chunk_size = max(1, len(items) // num_workers)
        chunks = []
        for i in range(0, len(items), chunk_size):
            chunks.append(items[i:i + chunk_size])
        
        # Ensure we have exactly num_workers chunks (pad with empty lists if needed)
        while len(chunks) < num_workers:
            chunks.append([])
        
        return chunks[:num_workers]
    
    def scrape(self, limit: Optional[int] = None, max_pages: int = 100) -> Dict[str, int]:
        """Run multi-threaded scraping workflow.
        
        Args:
            limit: Maximum number of hospitals to process (None = no limit)
            max_pages: Maximum number of listing pages to check (default: 100)
            
        Returns:
            Aggregated statistics dictionary
        """
        logger.info(f"Starting multi-threaded scraping with {self.num_threads} threads")
        
        # Step 1: Collect hospitals from listing pages (parallel)
        logger.info("Step 1: Collecting hospitals from listing pages...")
        page_numbers = list(range(1, max_pages + 1))
        page_chunks = self._distribute_work(page_numbers, self.num_threads)
        
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [executor.submit(self._step1_worker, chunk, limit, self.num_threads) for chunk in page_chunks if chunk]
            for future in as_completed(futures):
                try:
                    stats = future.result()
                    self._update_stats(stats)
                except Exception as exc:
                    logger.error(f"Step 1 worker failed: {exc}")
                    self._update_stats({"errors": 1})
        
        logger.info(f"Step 1 complete: {self.stats['hospitals']} hospitals collected")
        
        # Step 2: Enrich hospitals and collect doctors (parallel)
        logger.info("Step 2: Enriching hospitals and collecting doctors...")
        hospitals = self.mongo_client.get_hospitals_needing_enrichment(limit=limit)
        hospital_urls = [h["url"] for h in hospitals if h.get("url")]
        
        if hospital_urls:
            url_chunks = self._distribute_work(hospital_urls, self.num_threads)
            
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                futures = [executor.submit(self._step2_worker, chunk) for chunk in url_chunks if chunk]
                for future in as_completed(futures):
                    try:
                        stats = future.result()
                        self._update_stats(stats)
                    except Exception as exc:
                        logger.error(f"Step 2 worker failed: {exc}")
                        self._update_stats({"errors": 1})
        
        logger.info(f"Step 2 complete: {self.stats['hospitals']} hospitals enriched, {self.stats['doctors']} doctors collected")
        
        # Step 3: Process doctors (parallel)
        logger.info("Step 3: Processing doctor profiles...")
        doctors = self.mongo_client.get_doctors_needing_processing(limit=None)
        doctor_urls = [d["profile_url"] for d in doctors if d.get("profile_url")]
        
        if doctor_urls:
            url_chunks = self._distribute_work(doctor_urls, self.num_threads)
            
            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                futures = [executor.submit(self._step3_worker, chunk) for chunk in url_chunks if chunk]
                for future in as_completed(futures):
                    try:
                        stats = future.result()
                        self._update_stats(stats)
                    except Exception as exc:
                        logger.error(f"Step 3 worker failed: {exc}")
                        self._update_stats({"errors": 1})
        
        logger.info(f"Step 3 complete: {self.stats['doctors']} doctors processed")
        
        # Calculate totals
        self.stats["total"] = self.stats["hospitals"] + self.stats["doctors"]
        
        logger.info(
            "Multi-threaded scraping complete: total={}, hospitals={}, doctors={}, inserted={}, updated={}, skipped={}, errors={}",
            self.stats["total"],
            self.stats["hospitals"],
            self.stats["doctors"],
            self.stats["inserted"],
            self.stats["updated"],
            self.stats["skipped"],
            self.stats["errors"],
        )
        
        return self.stats

