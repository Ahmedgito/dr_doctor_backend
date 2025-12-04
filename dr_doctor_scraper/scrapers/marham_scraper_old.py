from __future__ import annotations

from typing import Dict, List, Optional
import time
from datetime import datetime

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
            # Extract name and URL from the main hospital link
            name_tag = card.select_one(".hosp_list_selected_hosp_name")
            if not name_tag:
                continue

            # Full text includes city at end (e.g., "Hashmanis Hospital - M A Jinnah Road, Karachi")
            full_name = clean_text(name_tag.get_text())
            href = name_tag.get("href") if name_tag.has_attr("href") else None
            url = href if href and href.startswith("http") else f"{BASE_URL}{href}" if href else None

            if not url or not full_name:
                continue

            # Split name and city: last part after comma is the city
            parts = full_name.rsplit(",", 1)
            name = clean_text(parts[0]) if parts else full_name
            city = clean_text(parts[1]) if len(parts) > 1 else "Karachi"

            # Extract address: look for p.text-sm elements (skip the empty one)
            address_paragraphs = card.select("p.text-sm")
            address = None
            for p in address_paragraphs:
                text = clean_text(p.get_text())
                if text:  # Skip empty paragraphs
                    address = text
                    break

            # Extract area from address (last part before the city)
            # e.g., "JM-75, Off M A Jinnah Road, Jacob Lines, Karachi" → "Jacob Lines"
            area = None
            if address:
                address_parts = address.rsplit(",", 1)
                if len(address_parts) > 1:
                    # Remove city from the end and get the last comma-separated part
                    remaining = address_parts[0]
                    remaining_parts = remaining.rsplit(",", 1)
                    area = clean_text(remaining_parts[1]) if len(remaining_parts) > 1 else None

            hospital = {
                "name": name,
                "city": city,
                "area": area,
                "address": address,
                "platform": self.PLATFORM,
                "url": url,
            }

            hospitals.append(hospital)

        return hospitals

    def _parse_full_hospital(self, html: str, url: str) -> dict:
        """Parse hospital page to extract enriched hospital information."""
        soup = BeautifulSoup(html, "html.parser")
        name = clean_text(self._first(soup.select_one(".hospital-title, h1, .hosp_name")))
        address = clean_text(self._first(soup.select_one(".address, .hospital-address, p.text-sm")))
        city = clean_text(self._first(soup.select_one(".city"))) or "Karachi"
        area = clean_text(self._first(soup.select_one(".area")))
        timing = clean_text(self._first(soup.select_one(".timing, .hospital-timing")))

        # Extract specialties list from the hospital page
        specialties: List[str] = []
        specialty_links = soup.select("a.hosp_prof_selected_speciality")
        for link in specialty_links:
            spec_text = clean_text(link.get_text())
            if spec_text and spec_text not in specialties:
                specialties.append(spec_text)

        # Extract "About" description from the hospital page
        # Look for the about section which typically starts with "About [Hospital Name]"
        about_text = None
        about_div = soup.select_one("div.row.justify-content-center")
        if about_div:
            # Extract all text content from paragraphs and lists in the about section
            paragraphs = about_div.select("p")
            about_parts = []
            for p in paragraphs:
                p_text = clean_text(p.get_text())
                if p_text:
                    about_parts.append(p_text)
            
            if about_parts:
                # Join first few paragraphs to create a summary (limit to ~500 chars for brevity)
                about_text = " ".join(about_parts[:3])  # Take first 3 paragraphs
                if len(about_text) > 500:
                    about_text = about_text[:500] + "..."

        return {
            "name": name,
            "address": address,
            "city": city,
            "area": area,
            "platform": self.PLATFORM,
            "url": url,
            "timing": timing,
            "specialties": specialties,
            "about": about_text,
        }

    @staticmethod
    def _first(el):
        return el.get_text(strip=True) if el else None

    # ------------------ Doctor extraction per hospital ------------------
    def _collect_doctor_cards_from_hospital(self, hospital_url: str) -> List[BeautifulSoup]:
        """Load the hospital page and attempt to collect all doctor cards.

        Strategy:
        - Load initial page and gather cards.
        - If a "Load More" button exists, click it repeatedly until it disappears
          or a safety limit is reached. Wait for loading buffer to disappear.
        - Also extract doctor names and URLs from the doctor list in the "About" section.
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
                        logger.info("Load More button clicked, waiting for content to load...")
                        
                        # Wait up to 20 seconds for loading buffer to appear and disappear
                        # First, wait for any loading spinner/buffer to appear
                        time.sleep(0.5)
                        
                        # Wait for loading buffer to disappear (up to 20 seconds)
                        max_wait = 30
                        waited = 0
                        loading_found = False
                        
                        while waited < max_wait:
                            # Check for various loading indicators
                            loading_spinner = self.page.query_selector(".loader, .loading, .spinner, [class*='load'], [class*='spin']")
                            
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
                            self.page.wait_for_load_state("networkidle", timeout=5000)
                        except:
                            pass
                        
                        time.sleep(0.5)
                        html = self.get_html()
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

        # Also extract doctors from the "About" section (Mumtaz Hospital format)
        doctor_list_links = soup.select("div.row.justify-content-center ul li a")
        for link in doctor_list_links:
            doctor_name = clean_text(link.get_text())
            doctor_url = link.get("href")
            if doctor_name and doctor_url:
                # Create a pseudo card object from the doctor list
                # This ensures we capture all doctors listed on the page
                logger.debug("Found doctor in list: {} -> {}", doctor_name, doctor_url)

        return cards

    def _extract_doctors_from_list(self, html: str, hospital_url: str) -> List[dict]:
        """Extract doctor names and URLs from the doctor list in the 'About' section.
        
        Format: <ul><li><a href="...">Dr. Name</a></li></ul>
        
        Returns list of dicts with keys: name, profile_url
        """
        soup = BeautifulSoup(html, "html.parser")
        doctors_from_list = []
        
        # Look for doctor list links in the About section
        doctor_list_links = soup.select("div.row.justify-content-center ul li a")
        for link in doctor_list_links:
            doctor_name = clean_text(link.get_text())
            doctor_href = link.get("href")
            
            if doctor_name and doctor_href:
                profile_url = f"{BASE_URL}{doctor_href}" if doctor_href.startswith("/") else doctor_href
                doctors_from_list.append({
                    "name": doctor_name,
                    "profile_url": profile_url,
                    "hospital_url": hospital_url,
                })
                logger.info("Found doctor in About list: {} -> {}", doctor_name, profile_url)
        
        return doctors_from_list

    def _parse_doctor_profile(self, html: str) -> dict:
        """Parse a doctor's profile page HTML for specialties and PMDC verification."""
        soup = BeautifulSoup(html, "html.parser")
        result = {"specialties": [], "pmdc_verified": False}

        # PMDC verified badge: look for a green text badge containing 'PMDC' or 'PMDC Verified'
        try:
            badge = soup.select_one("span.text-green.text-bold")
            if badge and "PMDC" in badge.get_text():
                result["pmdc_verified"] = True
        except Exception:
            result["pmdc_verified"] = False

        # Specialties: look for a strong.text-sm inside header or intro paragraph
        try:
            spec_tag = soup.select_one("p.mt-10 strong.text-sm, strong.text-sm")
            if spec_tag:
                text = spec_tag.get_text(separator=",")
                parts = [clean_text(p) for p in text.split(",") if clean_text(p)]
                result["specialties"] = parts
        except Exception:
            result["specialties"] = []

        # Also parse practice entries (per-hospital fee/timings/location)
        practices = []
        try:
            # Find section by header text
            sections = soup.select("section")
            target = None
            for sec in sections:
                h2 = sec.select_one("h2")
                if h2 and "Practice Address" in h2.get_text():
                    target = sec
                    break

            if not target:
                # fallback: search by class or h2 text
                target = soup.select_one("section.p-xy") or soup.select_one("section")

            if target:
                cards = target.select("div.mt-4.row.cursor-pointer")
                for c in cards:
                    try:
                        h_id = c.get("h_id")
                        d_id = c.get("d_id")
                        # hospital link (callcenter) if present
                        a = c.select_one("a.pc_practice_detail_card_dr_profile_tapped, a.oc_practice_detail_card_dr_profile_tapped")
                        hospital_url = None
                        if a and a.has_attr("href"):
                            hospital_url = a.get("href")
                            if hospital_url and hospital_url.startswith("/"):
                                hospital_url = f"{BASE_URL}{hospital_url}"

                        hospital_name_tag = c.select_one("h3")
                        hospital_name = clean_text(hospital_name_tag.get_text()) if hospital_name_tag else None

                        # area
                        area_tag = c.select_one("p:contains('Area:')")
                        area = None
                        if not area_tag:
                            # try generic p containing 'Area'
                            for p in c.select("p"):
                                if "Area:" in p.get_text():
                                    area_tag = p
                                    break
                        if area_tag:
                            area_text = area_tag.get_text()
                            # extract after 'Area:'
                            parts = area_text.split("Area:")
                            if len(parts) > 1:
                                area = clean_text(parts[1])

                        # fee
                        fee = None
                        fee_tag = None
                        for p in c.select("p"):
                            t = p.get_text()
                            if "Rs." in t or "Rs" in t:
                                fee_tag = p
                                break
                        if fee_tag:
                            digits = "".join(ch for ch in fee_tag.get_text() if ch.isdigit())
                            fee = int(digits) if digits else None

                        # timings: table rows under this card
                        timings = {}
                        for tr in c.select("table tr"):
                            tds = tr.select("td")
                            if len(tds) >= 2:
                                day = clean_text(tds[0].get_text())
                                time_text = clean_text(tds[1].get_text())
                                if day:
                                    timings[day] = time_text

                        # location: look for iframe with data-lat/data-lng
                        lat = None
                        lng = None
                        iframe = c.select_one("iframe[data-lat], iframe[data-src]")
                        if iframe:
                            lat_attr = iframe.get("data-lat") or iframe.get("data-lat")
                            lng_attr = iframe.get("data-lng") or iframe.get("data-lng")
                            try:
                                if lat_attr:
                                    lat = float(lat_attr)
                                if lng_attr:
                                    lng = float(lng_attr)
                            except Exception:
                                lat = None
                                lng = None

                        practices.append({
                            "h_id": h_id,
                            "d_id": d_id,
                            "hospital_name": hospital_name,
                            "hospital_url": hospital_url,
                            "area": area,
                            "fee": fee,
                            "timings": timings,
                            "lat": lat,
                            "lng": lng,
                        })
                    except Exception:
                        continue
        except Exception:
            pass

        result["practices"] = practices

        # Parse qualifications from Qualification table
        qualifications = []
        try:
            # Find the Qualification section (h2 with text "Qualification")
            target_section = None
            for div in soup.select("div"):
                h2 = div.select_one("h2")
                if h2 and "Qualification" in h2.get_text():
                    target_section = div
                    break

            if target_section:
                # Find table within this section
                table = target_section.select_one("table")
                if table:
                    # Parse tbody rows, extract institute (td[0]) and degree (td[1])
                    tbody = table.select_one("tbody")
                    if tbody:
                        for tr in tbody.select("tr"):
                            tds = tr.select("td")
                            if len(tds) >= 2:
                                institute = clean_text(tds[0].get_text())
                                degree = clean_text(tds[1].get_text())
                                if institute and degree:
                                    qualifications.append({
                                        "institute": institute,
                                        "degree": degree,
                                    })
        except Exception:
            pass

        result["qualifications"] = qualifications

        # Parse experience: years of practice and work history
        experience_years = None
        work_history = []

        try:
            # Extract years from intro: look for "X Yrs Experience" pattern
            for p in soup.select("p"):
                text = p.get_text()
                if "Yrs Experience" in text or "Years Experience" in text:
                    # Extract number from text like "20 Yrs Experience"
                    digits = "".join(ch for ch in text if ch.isdigit())
                    if digits:
                        experience_years = int(digits)
                    break
        except Exception:
            pass

        try:
            # Find the Experience section (h2 with text "Experience")
            target_section = None
            for div in soup.select("div"):
                h2 = div.select_one("h2")
                if h2 and "Experience" in h2.get_text() and "Qualification" not in h2.get_text():
                    target_section = div
                    break

            if target_section:
                # Find table within this section
                table = target_section.select_one("table")
                if table:
                    # Parse tbody rows, extract institute (td[0]) and designation (td[1])
                    tbody = table.select_one("tbody")
                    if tbody:
                        for tr in tbody.select("tr"):
                            tds = tr.select("td")
                            if len(tds) >= 2:
                                institute = clean_text(tds[0].get_text())
                                designation = clean_text(tds[1].get_text())
                                if institute and designation:
                                    work_history.append({
                                        "institute": institute,
                                        "designation": designation,
                                    })
        except Exception:
            pass

        result["experience_years"] = experience_years
        result["work_history"] = work_history
        return result

    def _merge_doctor_records(self, existing: dict, new_model: DoctorModel) -> Optional[dict]:
        """Merge existing doctor document with data from new_model.

        Returns a dict of fields to set (for MongoDB $set) or None if no change.
        - Preserves existing richer fields when new_model has empty/None values.
        - Merges `hospitals` lists deduplicating by URL.
        """
        if not existing:
            return new_model.dict()

        existing_data = {k: v for k, v in existing.items() if k not in ("_id", "scraped_at")}
        new_data = {k: v for k, v in new_model.dict().items() if k not in ("_id", "scraped_at")}

        updated: dict = {}

        # Merge hospitals (list of dicts with possible fee/timings)
        existing_hospitals = existing_data.get("hospitals") or []
        if not isinstance(existing_hospitals, list):
            existing_hospitals = []
        new_hospitals = new_data.get("hospitals") or []

        # Build mapping by url (fallback to name if url missing)
        merged_map = {}
        for h in existing_hospitals:
            if isinstance(h, dict):
                key = h.get("url") or h.get("name")
                if key:
                    merged_map[key] = dict(h)

        for h in new_hospitals:
            if not isinstance(h, dict):
                continue
            key = h.get("url") or h.get("name")
            if not key:
                continue
            if key in merged_map:
                # update fields if new provides non-empty values
                for fk, fv in h.items():
                    if fv is None or (isinstance(fv, (list, str)) and len(fv) == 0):
                        continue
                    if merged_map[key].get(fk) != fv:
                        merged_map[key][fk] = fv
            else:
                merged_map[key] = dict(h)

        merged_hospitals = list(merged_map.values())
        if merged_hospitals != existing_hospitals:
            updated["hospitals"] = merged_hospitals

        # For other fields, prefer non-empty values from new_data; otherwise keep existing
        for key, val in new_data.items():
            if key == "hospitals":
                continue
            if val is None or (isinstance(val, (list, str)) and len(val) == 0):
                # skip empty new values
                continue
            if existing_data.get(key) != val:
                updated[key] = val

        if not updated:
            return None

        updated["scraped_at"] = datetime.utcnow()
        return updated

    def _upsert_hospital_practice(self, practice: dict, doctor: DoctorModel) -> None:
        """Ensure hospital doc exists and record this doctor's practice info for that hospital.

        - Upserts hospital basic info using `update_hospital`.
        - Merges/updates the hospital's `doctors` list with an entry for this doctor (profile_url).
        """
        if not practice:
            return

        hosp_url = practice.get("hospital_url")
        hosp_name = practice.get("hospital_name") or ""
        area = practice.get("area")
        fee = practice.get("fee")
        timings = practice.get("timings") or {}
        lat = practice.get("lat")
        lng = practice.get("lng")

        # Build minimal hospital doc to upsert
        hosp_doc = {
            "name": hosp_name,
            "platform": self.PLATFORM,
            "url": hosp_url,
            "address": area or None,
        }

        # Add location if present
        if lat is not None and lng is not None:
            hosp_doc["location"] = {"lat": lat, "lng": lng}

        try:
            # Upsert hospital (will create if missing)
            if hasattr(self.mongo_client, "update_hospital"):
                self.mongo_client.update_hospital(hosp_url, hosp_doc)
            else:
                # fallback insert
                try:
                    self.mongo_client.insert_hospital(HospitalModel(**hosp_doc).dict())
                except Exception:
                    pass

            # Now merge doctor entry into hospital.doctors
            hosp_filter = {"url": hosp_url} if hosp_url else {"name": hosp_name, "address": area}
            hosp_record = self.mongo_client.hospitals.find_one(hosp_filter) or {}
            existing_doctors = hosp_record.get("doctors") or []

            # Doctor entry to upsert into hospital.doctors
            doctor_entry = {
                "profile_url": doctor.profile_url,
                "name": doctor.name,
                "fee": fee,
                "timings": timings,
                "practice_id": practice.get("h_id"),
            }

            updated = False
            for i, d in enumerate(existing_doctors):
                if isinstance(d, dict) and d.get("profile_url") == doctor.profile_url:
                    # merge fields
                    if d.get("fee") != fee:
                        d["fee"] = fee
                        updated = True
                    if d.get("timings") != timings:
                        d["timings"] = timings
                        updated = True
                    if d.get("name") != doctor.name:
                        d["name"] = doctor.name
                        updated = True
                    existing_doctors[i] = d
                    break
            else:
                # not found, append
                existing_doctors.append(doctor_entry)
                updated = True

            # If location present, ensure hospital doc contains it
            if (lat is not None and lng is not None) and hosp_record.get("location") != {"lat": lat, "lng": lng}:
                hosp_record["location"] = {"lat": lat, "lng": lng}
                updated = True

            if updated:
                # write back doctors and location fields
                update_fields = {"doctors": existing_doctors}
                if hosp_record.get("location"):
                    update_fields["location"] = hosp_record.get("location")
                try:
                    self.mongo_client.hospitals.update_one(hosp_filter, {"$set": update_fields}, upsert=True)
                except Exception:
                    logger.warning("Failed to update hospital doctors for {}", hosp_name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to upsert hospital practice {}: {}", practice, exc)

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

            # Create a minimal doctor model; hospital affiliations are set later
            model = DoctorModel(
                name=name,
                specialty=specialty,
                fees=None,
                city="Karachi",
                area=None,
                hospital=None,
                hospitals=None,
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

            hospitals = self._parse_hospital_cards(html)
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
                                logger.debug("Insert minimal hospital exception: {}", exc)
                except Exception:  # noqa: BLE001
                    logger.warning("Could not insert minimal hospital: {}", h.get("name"))

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
                enriched = self._parse_full_hospital(hosp_html, hosp_url)

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
                cards = self._collect_doctor_cards_from_hospital(hosp_url)
                for card in cards:
                    stats["total"] += 1

                    doctor = self._parse_doctor_card(card, hosp_url)
                    if not doctor:
                        stats["skipped"] += 1
                        continue

                    # Attach hospital affiliation (name + url)
                    affiliation = {"name": enriched.get("name", ""), "url": hosp_url}
                    doctor.hospitals = [affiliation]
                    doctor.hospital = enriched.get("name", "")

                    # Enrich doctor from profile page if possible
                    try:
                        if doctor.profile_url:
                            self.load_page(doctor.profile_url)
                            self.wait_for("body")
                            doc_html = self.get_html()
                            details = self._parse_doctor_profile(doc_html)
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
                            # Process practices: upsert hospital records and attach to doctor.hospitals
                            for practice in details.get("practices", []):
                                try:
                                    # add hospital-affiliation info to doctor.hospitals
                                    if not doctor.hospitals:
                                        doctor.hospitals = []
                                    hosp_entry = {
                                        "name": practice.get("hospital_name"),
                                        "url": practice.get("hospital_url"),
                                        "fee": practice.get("fee"),
                                        "timings": practice.get("timings"),
                                        "practice_id": practice.get("h_id"),
                                    }
                                    # avoid duplicates by url
                                    existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                                    if practice.get("hospital_url") not in existing_urls:
                                        doctor.hospitals.append(hosp_entry)

                                    # Upsert hospital and add doctor entry into hospital.doctors
                                    self._upsert_hospital_practice(practice, doctor)
                                except Exception:
                                    continue
                    except Exception:
                        logger.debug("Could not load or parse doctor profile: {}", doctor.profile_url)

                    # Skip if we've already seen this doctor URL in this run
                    if doctor.profile_url in seen_doctor_urls:
                        logger.info("Skipping duplicate doctor in this run: {}", doctor.profile_url)
                        stats["skipped"] += 1
                        continue

                    seen_doctor_urls.add(doctor.profile_url)

                    # Upsert doctor with merge
                    if self.mongo_client.doctor_exists(doctor.profile_url):
                        existing_doctor = self.mongo_client.doctors.find_one({"profile_url": doctor.profile_url})
                        merged = self._merge_doctor_records(existing_doctor, doctor)
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

                # Also extract and save doctors from the About section doctor list
                doctors_from_list = self._extract_doctors_from_list(hosp_html, hosp_url)
                for doctor_info in doctors_from_list:
                    stats["total"] += 1

                    profile_url = doctor_info["profile_url"]

                    # Skip if we've already seen this doctor URL in this run
                    if profile_url in seen_doctor_urls:
                        logger.info("Skipping duplicate doctor in this run: {}", profile_url)
                        stats["skipped"] += 1
                        continue

                    seen_doctor_urls.add(profile_url)

                    # Create minimal DoctorModel from list entry (name + URL only)
                    affiliation = {"name": enriched.get("name", ""), "url": hosp_url}
                    doctor = DoctorModel(
                        name=doctor_info["name"],
                        specialty=[],
                        fees=None,
                        city="Karachi",
                        area="",
                        hospital=None,
                        hospitals=[affiliation],
                        address=enriched.get("address", ""),
                        rating=None,
                        experience="",
                        profile_url=profile_url,
                        platform=self.PLATFORM,
                    )

                    # Enrich doctor from profile page if possible (list entries may be minimal)
                    try:
                        if profile_url:
                            self.load_page(profile_url)
                            self.wait_for("body")
                            doc_html = self.get_html()
                            details = self._parse_doctor_profile(doc_html)
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
                            # Process practices: upsert hospital records and attach to doctor.hospitals
                            for practice in details.get("practices", []):
                                try:
                                    # add hospital-affiliation info to doctor.hospitals
                                    if not doctor.hospitals:
                                        doctor.hospitals = []
                                    hosp_entry = {
                                        "name": practice.get("hospital_name"),
                                        "url": practice.get("hospital_url"),
                                        "fee": practice.get("fee"),
                                        "timings": practice.get("timings"),
                                        "practice_id": practice.get("h_id"),
                                    }
                                    # avoid duplicates by url
                                    existing_urls = {h.get("url") for h in doctor.hospitals if isinstance(h, dict) and h.get("url")}
                                    if practice.get("hospital_url") not in existing_urls:
                                        doctor.hospitals.append(hosp_entry)

                                    # Upsert hospital and add doctor entry into hospital.doctors
                                    self._upsert_hospital_practice(practice, doctor)
                                except Exception:
                                    continue
                    except Exception:
                        logger.debug("Could not load or parse doctor profile from list: {}", profile_url)

                    if self.mongo_client.doctor_exists(profile_url):
                        existing_doctor = self.mongo_client.doctors.find_one({"profile_url": profile_url})
                        merged = self._merge_doctor_records(existing_doctor, doctor)
                        if merged:
                            try:
                                self.mongo_client.doctors.update_one({"profile_url": profile_url}, {"$set": merged})
                                stats["updated"] += 1
                            except Exception as exc:  # noqa: BLE001
                                logger.warning("Failed to update doctor {}: {}", profile_url, exc)
                        else:
                            stats["skipped"] += 1
                    else:
                        try:
                            self.mongo_client.insert_doctor(doctor.dict())
                            stats["inserted"] += 1
                            stats["doctors"] += 1
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Failed to insert doctor {}: {}", profile_url, exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed processing hospital {}: {}", hosp_url, exc)

            # polite pause between hospitals
            time.sleep(1)

        logger.info("Marham scraping finished: {}", stats)
        return stats
