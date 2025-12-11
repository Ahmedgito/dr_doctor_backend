"""Multi-threaded wrapper for Marham scraper to speed up data collection."""

from __future__ import annotations

import threading
import time
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
    
    def _step1_worker(self, city_queue: Queue, limit: Optional[int]) -> Dict[str, int]:
        """Worker thread for Step 1: Collect hospitals from listing pages.
        
        Uses a queue-based approach where threads pull cities dynamically.
        This ensures threads stay busy even when cities have varying page counts.
        
        Args:
            city_queue: Thread-safe queue containing city documents to process
            limit: Global limit on hospitals to collect (None = no limit)
            
        Returns:
            Statistics dictionary
        """
        worker_stats = {"hospitals": 0, "errors": 0}
        thread_id = threading.current_thread().ident
        BASE_URL = "https://www.marham.pk"
        
        try:
            with MarhamScraper(
                mongo_client=self.mongo_client,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
                max_retries=self.max_retries,
            ) as scraper:
                logger.info(f"[Thread {thread_id}] Starting Step 1 worker (queue-based)")
                
                total_collected = 0
                cities_processed = 0
                
                # Keep pulling cities from queue until it's empty
                while True:
                    try:
                        # Get next city from queue (timeout after 1 second to check if queue is empty)
                        city_doc = city_queue.get(timeout=1)
                    except:
                        # Queue is empty, we're done
                        break
                    
                    # Check global limit
                    if limit and total_collected >= limit:
                        # Put city back in queue for other threads
                        city_queue.put(city_doc)
                        break
                    
                    city_name = city_doc.get("name", "Unknown")
                    city_url = city_doc.get("url")
                    
                    if not city_url:
                        city_queue.task_done()
                        continue
                    
                    logger.info(f"[Thread {thread_id}] Processing city: {city_name} ({city_url})")
                    
                    # Extract city slug from URL
                    if "/hospitals/" in city_url:
                        city_slug = city_url.split("/hospitals/")[-1].split("?")[0].strip()
                        if not city_slug:
                            logger.warning(f"[Thread {thread_id}] Empty city slug for: {city_url}")
                            city_queue.task_done()
                            continue
                    else:
                        logger.warning(f"[Thread {thread_id}] Invalid city URL: {city_url}")
                        city_queue.task_done()
                        continue
                    
                    page = 1
                    city_collected = 0
                    
                    # Process all pages for this city
                    while True:
                        # Check global limit
                        if limit and total_collected >= limit:
                            break
                        
                        # Build URL for this city and page
                        url = f"{BASE_URL}/hospitals/{city_slug}?page={page}"
                        logger.debug(f"[Thread {thread_id}] Loading page {page} for city {city_name}: {url}")
                        
                        # Record page in pages collection
                        self.mongo_client.upsert_page(
                            url=url,
                            city_name=city_name,
                            city_url=city_url,
                            page_number=page
                        )
                        
                        try:
                            scraper.load_page(url)
                            scraper.wait_for("body")
                            html = scraper.get_html()
                            # Mark page as success
                            self.mongo_client.mark_page_success(url)
                        except Exception as exc:
                            logger.warning(f"[Thread {thread_id}] Failed to load page {page} for {city_name}: {exc}")
                            # Mark page as failed (will be retried later)
                            self.mongo_client.mark_page_failed(url, str(exc))
                            # Continue to next page instead of breaking
                            page += 1
                            continue
                        
                        hospitals = scraper.hospital_parser.parse_hospital_cards(html)
                        if not hospitals:
                            logger.info(f"[Thread {thread_id}] No more hospitals found on page {page} for city {city_name}")
                            break
                        
                        # Process hospitals from this page
                        for h in hospitals:
                            if limit and total_collected >= limit:
                                break
                            
                            if not h.get("name") or not h.get("url"):
                                continue
                            
                            hospital_url = h.get("url")
                            
                            # Check if hospital already exists
                            existing = self.mongo_client.hospitals.find_one({"url": hospital_url})
                            if existing:
                                city_collected += 1
                                continue
                            
                            # Extract location if possible
                            if scraper.page:
                                try:
                                    location = scraper.hospital_parser.extract_location_from_card(
                                        scraper.page, hospital_url
                                    )
                                    if location:
                                        h["location"] = location
                                except Exception:
                                    pass
                            
                            # Save minimal hospital record
                            try:
                                minimal = {
                                    "name": h.get("name"),
                                    "platform": "marham",
                                    "url": hospital_url,
                                    "address": h.get("address"),
                                    "city": h.get("city") or city_name,
                                    "area": h.get("area"),
                                    "scrape_status": "pending"
                                }
                                if h.get("location"):
                                    minimal["location"] = h["location"]
                                
                                if self.mongo_client.update_hospital(hospital_url, minimal):
                                    worker_stats["hospitals"] += 1
                                    city_collected += 1
                                    total_collected += 1
                                    logger.debug(f"[Thread {thread_id}] Collected hospital: {h.get('name')}")
                            except Exception as exc:
                                logger.warning(f"[Thread {thread_id}] Failed to save hospital: {exc}")
                                worker_stats["errors"] += 1
                        
                        if limit and total_collected >= limit:
                            break
                        
                        page += 1
                        time.sleep(0.5)  # Polite pause between pages
                    
                    # Mark city as scraped if we collected hospitals
                    if city_collected > 0:
                        self.mongo_client.update_city_status(city_url, "scraped")
                        logger.info(f"[Thread {thread_id}] City {city_name} completed: {city_collected} hospitals")
                    
                    cities_processed += 1
                    city_queue.task_done()
                
                logger.info(f"[Thread {thread_id}] Step 1 worker completed: {worker_stats['hospitals']} hospitals from {cities_processed} cities")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Step 1 worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _step1_retry_pages_worker(self, page_queue: Queue) -> Dict[str, int]:
        """Worker thread for retrying failed pages.
        
        Uses a queue-based approach where threads pull pages dynamically.
        
        Args:
            page_queue: Thread-safe queue containing page documents to retry
            
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
                logger.info(f"[Thread {thread_id}] Starting retry worker (queue-based)")
                
                pages_processed = 0
                
                # Keep pulling pages from queue until it's empty
                while True:
                    try:
                        # Get next page from queue (timeout after 1 second to check if queue is empty)
                        page_doc = page_queue.get(timeout=1)
                    except:
                        # Queue is empty, we're done
                        break
                    url = page_doc.get("url")
                    city_name = page_doc.get("city_name", "Unknown")
                    page_number = page_doc.get("page_number", 0)
                    
                    if not url:
                        page_queue.task_done()
                        pages_processed += 1
                        continue
                    
                    logger.info(f"[Thread {thread_id}] Retrying page {page_number} for city {city_name}: {url}")
                    
                    # Mark as retrying
                    self.mongo_client.mark_page_retrying(url)
                    
                    try:
                        scraper.load_page(url)
                        scraper.wait_for("body")
                        html = scraper.get_html()
                        
                        hospitals = scraper.hospital_parser.parse_hospital_cards(html)
                        if not hospitals:
                            logger.debug(f"[Thread {thread_id}] No hospitals found on retried page: {url}")
                            self.mongo_client.mark_page_success(url)
                            page_queue.task_done()
                            pages_processed += 1
                            continue
                        
                        # Process hospitals
                        page_collected = 0
                        for h in hospitals:
                            if not h.get("name") or not h.get("url"):
                                continue
                            
                            hospital_url = h.get("url")
                            
                            # Check if hospital already exists
                            existing = self.mongo_client.hospitals.find_one({"url": hospital_url})
                            if existing:
                                page_collected += 1
                                continue
                            
                            # Extract location if possible
                            if scraper.page:
                                try:
                                    location = scraper.hospital_parser.extract_location_from_card(
                                        scraper.page, hospital_url
                                    )
                                    if location:
                                        h["location"] = location
                                except Exception:
                                    pass
                            
                            # Save minimal hospital record
                            try:
                                minimal = {
                                    "name": h.get("name"),
                                    "platform": "marham",
                                    "url": hospital_url,
                                    "address": h.get("address"),
                                    "city": h.get("city") or city_name,
                                    "area": h.get("area"),
                                    "scrape_status": "pending"
                                }
                                if h.get("location"):
                                    minimal["location"] = h["location"]
                                
                                if self.mongo_client.update_hospital(hospital_url, minimal):
                                    worker_stats["hospitals"] += 1
                                    page_collected += 1
                            except Exception as exc:
                                logger.warning(f"[Thread {thread_id}] Failed to save hospital: {exc}")
                                worker_stats["errors"] += 1
                        
                        # Mark page as success
                        self.mongo_client.mark_page_success(url)
                        logger.info(f"[Thread {thread_id}] Successfully retried page: {url} ({page_collected} hospitals)")
                        
                    except Exception as exc:
                        logger.warning(f"[Thread {thread_id}] Failed to retry page {url}: {exc}")
                        self.mongo_client.mark_page_failed(url, str(exc))
                        worker_stats["errors"] += 1
                    
                    pages_processed += 1
                    page_queue.task_done()
                    time.sleep(0.5)  # Polite pause
                
                logger.info(f"[Thread {thread_id}] Retry worker completed: {worker_stats['hospitals']} hospitals from {pages_processed} pages")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Retry worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _step2_worker(self, hospital_queue: Queue) -> Dict[str, int]:
        """Worker thread for Step 2: Enrich hospitals and collect doctors.
        
        Uses a queue-based approach where threads pull hospitals dynamically.
        This ensures threads stay busy even when hospitals have varying processing times.
        
        Args:
            hospital_queue: Thread-safe queue containing hospital URLs to process
            
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
                logger.info(f"[Thread {thread_id}] Starting Step 2 worker (queue-based)")
                
                hospitals_processed = 0
                
                # Keep pulling hospitals from queue until it's empty
                while True:
                    try:
                        # Get next hospital from queue (timeout after 1 second to check if queue is empty)
                        hospital_url = hospital_queue.get(timeout=1)
                    except:
                        # Queue is empty, we're done
                        break
                    
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
                    finally:
                        hospitals_processed += 1
                        hospital_queue.task_done()
                
                logger.info(f"[Thread {thread_id}] Step 2 worker completed: {worker_stats['hospitals']} hospitals, {worker_stats['doctors']} doctors from {hospitals_processed} hospitals")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Step 2 worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _step3_worker(self, doctor_queue: Queue) -> Dict[str, int]:
        """Worker thread for Step 3: Process doctor profiles.
        
        Uses a queue-based approach where threads pull doctors dynamically.
        This ensures threads stay busy even when doctors have varying processing times.
        
        Args:
            doctor_queue: Thread-safe queue containing doctor profile URLs to process
            
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
                logger.info(f"[Thread {thread_id}] Starting Step 3 worker (queue-based)")
                
                doctors_processed = 0
                
                # Keep pulling doctors from queue until it's empty
                while True:
                    try:
                        # Get next doctor from queue (timeout after 1 second to check if queue is empty)
                        doctor_url = doctor_queue.get(timeout=1)
                    except:
                        # Queue is empty, we're done
                        break
                    
                    try:
                        # Get minimal doctor record from database
                        doctor_doc = self.mongo_client.doctors.find_one({"profile_url": doctor_url})
                        if not doctor_doc:
                            logger.warning(f"[Thread {thread_id}] Doctor not found in DB: {doctor_url}")
                            doctors_processed += 1
                            doctor_queue.task_done()
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
                        
                        # Use the existing doctor_doc we already fetched (line 257)
                        # If it exists, merge and update; otherwise insert
                        if doctor_doc:
                            # Doctor exists - merge and update
                            merged = scraper.data_merger.merge_doctor_records(doctor_doc, doctor)
                            if merged:
                                result = self.mongo_client.doctors.update_one(
                                    {"profile_url": doctor.profile_url},
                                    {"$set": merged}
                                )
                                if result.modified_count > 0:
                                    worker_stats["updated"] += 1
                                else:
                                    # Update didn't change anything (shouldn't happen, but handle it)
                                    worker_stats["skipped"] += 1
                                worker_stats["doctors"] += 1
                            else:
                                # No changes needed - merge returned None
                                worker_stats["skipped"] += 1
                                worker_stats["doctors"] += 1
                        else:
                            # Doctor doesn't exist - insert it
                            # (This shouldn't happen since we skip if not found, but handle it anyway)
                            if self.mongo_client.insert_doctor(doctor.dict()):
                                worker_stats["inserted"] += 1
                                worker_stats["doctors"] += 1
                            else:
                                worker_stats["errors"] += 1
                        
                        # Update status regardless of whether we updated or skipped
                        self.mongo_client.update_doctor_status(doctor.profile_url, "processed")
                        
                    except Exception as exc:
                        logger.error(f"[Thread {thread_id}] Error processing doctor {doctor_url}: {exc}")
                        worker_stats["errors"] += 1
                        continue
                
                logger.info(f"[Thread {thread_id}] Step 3 worker completed: {worker_stats['doctors']} doctors")
                
        except Exception as exc:
            logger.error(f"[Thread {thread_id}] Step 3 worker failed: {exc}")
            worker_stats["errors"] += 1
        
        return worker_stats
    
    def _get_processed_pages(self) -> set:
        """Get set of page numbers that have already been processed.
        
        We track this by checking which hospitals have a 'source_page' field,
        or by checking the hospitals collection for any hospitals.
        """
        try:
            # Get all hospitals and extract page numbers from their URLs or metadata
            # For now, we'll use a simple approach: check if hospitals exist
            # A better approach would be to store page numbers in a separate collection
            hospitals = list(self.mongo_client.hospitals.find({}, {"url": 1}))
            # Since we don't track pages directly, return empty set for now
            # This will be improved in a future version
            return set()
        except Exception:
            return set()
    
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
    
    def scrape(self, limit: Optional[int] = None, max_pages: int = 500, step: Optional[int] = None) -> Dict[str, int]:
        """Run multi-threaded scraping workflow.
        
        Args:
            limit: Maximum number of hospitals to process (None = no limit)
            max_pages: Maximum number of listing pages to check (default: 500)
            step: Run only a specific step (0, 1, 2, or 3). None = run all steps
            
        Returns:
            Aggregated statistics dictionary
        """
        logger.info(f"Starting multi-threaded scraping with {self.num_threads} threads")
        
        if step is not None:
            logger.info(f"Running only Step {step}")
        
        # Step 0: Collect cities (single-threaded, simple HTTP request)
        if step is None or step == 0:
            logger.info("Step 0: Collecting cities from hospitals page...")
            from scrapers.marham.collectors.city_collector import CityCollector
            city_collector = CityCollector()
            cities = city_collector.collect_cities()
            
            cities_collected = 0
            for city_data in cities:
                name = city_data.get("name")
                url = city_data.get("url")
                if name and url:
                    if self.mongo_client.upsert_city(name, url):
                        cities_collected += 1
                        logger.info("Saved city: {} -> {}", name, url)
            
            self._update_stats({"cities": cities_collected})
            logger.info("Step 0 completed: {} cities collected", cities_collected)
        
        # Step 1: Collect hospitals from listing pages (per city, parallel)
        if step is None or step == 1:
            logger.info("Step 1: Collecting hospitals from listing pages (per city)...")
            
            # First, process failed/pending pages using queue-based approach
            failed_pages = self.mongo_client.get_pages_needing_retry()
            if failed_pages:
                logger.info(f"Found {len(failed_pages)} pages that need retry (using dynamic queue)")
                
                # Create queue and add all pages
                page_queue = Queue()
                for page in failed_pages:
                    page_queue.put(page)
                
                # Process pages in parallel using queue (threads pull pages dynamically)
                with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                    futures = [
                        executor.submit(self._step1_retry_pages_worker, page_queue) 
                        for _ in range(self.num_threads)
                    ]
                    for future in as_completed(futures):
                        try:
                            stats = future.result()
                            self._update_stats(stats)
                        except Exception as exc:
                            logger.error(f"Step 1 retry pages worker failed: {exc}")
                            self._update_stats({"errors": 1})
                
                # Wait for all tasks to complete
                page_queue.join()
            
            # Then, get all cities that need scraping
            cities_cursor = self.mongo_client.get_cities_needing_scraping()
            cities = list(cities_cursor)
            
            if not cities:
                logger.warning("No cities found in database. Run Step 0 first to collect cities.")
            else:
                logger.info(f"Found {len(cities)} cities to process (using dynamic queue distribution)")
                
                # Create queue and add all cities
                city_queue = Queue()
                for city in cities:
                    city_queue.put(city)
                
                # Process cities in parallel using queue (threads pull cities dynamically)
                # This ensures threads stay busy - when one finishes a small city, it immediately
                # picks up the next city, preventing idle time
                with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                    futures = [
                        executor.submit(self._step1_worker, city_queue, limit) 
                        for _ in range(self.num_threads)
                    ]
                    for future in as_completed(futures):
                        try:
                            stats = future.result()
                            self._update_stats(stats)
                        except Exception as exc:
                            logger.error(f"Step 1 worker failed: {exc}")
                            self._update_stats({"errors": 1})
                
                # Wait for all tasks to complete
                city_queue.join()
                
                logger.info(f"Step 1 complete: {self.stats['hospitals']} hospitals collected across all cities")
        
        # Step 2: Enrich hospitals and collect doctors (parallel, queue-based)
        if step is None or step == 2:
            logger.info("Step 2: Enriching hospitals and collecting doctors...")
            hospitals = list(self.mongo_client.get_hospitals_needing_enrichment(limit=limit))
            hospital_urls = [h["url"] for h in hospitals if h.get("url")]
            
            logger.info(f"Found {len(hospital_urls)} hospitals needing enrichment (using dynamic queue distribution)")
            
            if hospital_urls:
                # Create queue and add all hospital URLs
                hospital_queue = Queue()
                for url in hospital_urls:
                    hospital_queue.put(url)
                
                # Process hospitals in parallel using queue (threads pull hospitals dynamically)
                with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                    futures = [
                        executor.submit(self._step2_worker, hospital_queue) 
                        for _ in range(self.num_threads)
                    ]
                    for future in as_completed(futures):
                        try:
                            stats = future.result()
                            self._update_stats(stats)
                        except Exception as exc:
                            logger.error(f"Step 2 worker failed: {exc}")
                            self._update_stats({"errors": 1})
                
                # Wait for all tasks to complete
                hospital_queue.join()
            
            logger.info(f"Step 2 complete: {self.stats['hospitals']} hospitals enriched, {self.stats['doctors']} doctors collected")
        
        # Step 3: Process doctors (parallel)
        if step is None or step == 3:
            logger.info("Step 3: Processing doctor profiles...")
            doctors = list(self.mongo_client.get_doctors_needing_processing(limit=None))
            doctor_urls = [d["profile_url"] for d in doctors if d.get("profile_url")]
            
            logger.info(f"Found {len(doctor_urls)} doctors needing processing (using dynamic queue distribution)")
            
            if doctor_urls:
                # Create queue and add all doctor URLs
                doctor_queue = Queue()
                for url in doctor_urls:
                    doctor_queue.put(url)
                
                # Process doctors in parallel using queue (threads pull doctors dynamically)
                with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                    futures = [
                        executor.submit(self._step3_worker, doctor_queue) 
                        for _ in range(self.num_threads)
                    ]
                    for future in as_completed(futures):
                        try:
                            stats = future.result()
                            self._update_stats(stats)
                        except Exception as exc:
                            logger.error(f"Step 3 worker failed: {exc}")
                            self._update_stats({"errors": 1})
                
                # Wait for all tasks to complete
                doctor_queue.join()
            
            # Step 3 doctors count should be sum of updated + skipped + inserted
            # Note: errors are not counted in doctors processed
            step3_doctors = self.stats["updated"] + self.stats["skipped"] + self.stats["inserted"]
            logger.info(f"Step 3 complete: {step3_doctors} doctors processed (updated: {self.stats['updated']}, skipped: {self.stats['skipped']}, inserted: {self.stats['inserted']}, errors: {self.stats.get('errors', 0)})")
            
            # Update doctors counter to reflect actual processed count
            self.stats["doctors"] = step3_doctors
        
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

