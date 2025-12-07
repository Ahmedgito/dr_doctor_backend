"""Handler for hospital practice upserting and doctor-hospital relationships."""

from __future__ import annotations

from typing import Optional
from bs4 import BeautifulSoup

from scrapers.database.mongo_client import MongoClientManager
from scrapers.models.doctor_model import DoctorModel
from scrapers.models.hospital_model import HospitalModel
from scrapers.utils.url_parser import is_hospital_url, parse_hospital_url
from scrapers.logger import logger


class HospitalPracticeHandler:
    """Handles upserting hospital practices and managing doctor-hospital relationships."""

    PLATFORM = "marham"

    def __init__(self, mongo_client: MongoClientManager):
        """Initialize with MongoDB client.
        
        Args:
            mongo_client: MongoClientManager instance
        """
        self.mongo_client = mongo_client

    def upsert_hospital_practice(self, practice: dict, doctor: DoctorModel) -> None:
        """Ensure hospital doc exists and record this doctor's practice info for that hospital.

        - Upserts hospital basic info using `update_hospital`.
        - Merges/updates the hospital's `doctors` list with an entry for this doctor (profile_url).

        Args:
            practice: Dictionary with hospital practice information
            doctor: DoctorModel instance
        """
        if not practice:
            return

        hosp_url = practice.get("hospital_url")
        
        # Only process if it's a real hospital URL
        if not hosp_url or not is_hospital_url(hosp_url):
            return

        hosp_name = practice.get("hospital_name") or ""
        area = practice.get("area")
        fee = practice.get("fee")
        timings = practice.get("timings") or {}
        lat = practice.get("lat")
        lng = practice.get("lng")

        # Parse city, name, area from URL
        url_parts = parse_hospital_url(hosp_url)
        
        # Build minimal hospital doc to upsert
        hosp_doc = {
            "name": hosp_name or url_parts.get("name") or "",
            "platform": self.PLATFORM,
            "url": hosp_url,
            "city": url_parts.get("city"),
            "area": area or url_parts.get("area"),
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
            # Always use URL for lookup (most reliable)
            hosp_filter = {"url": hosp_url}
            hosp_record = self.mongo_client.hospitals.find_one(hosp_filter) or {}
            existing_doctors = hosp_record.get("doctors") or []
            
            # If doctors is a list of simple dicts (from Phase 1), convert to full format
            if existing_doctors and isinstance(existing_doctors[0], dict) and "fee" not in existing_doctors[0]:
                # Phase 1 format: just name and profile_url
                # Convert to Phase 2 format with fee and timings
                pass  # We'll merge below

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

