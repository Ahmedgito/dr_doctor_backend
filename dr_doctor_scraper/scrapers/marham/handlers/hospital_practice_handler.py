"""Handler for hospital practice upserting and doctor-hospital relationships."""

from __future__ import annotations

import re
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

    def find_hospital_by_name(self, hospital_name: str) -> Optional[str]:
        """Find hospital URL by matching name in the collection.
        
        Args:
            hospital_name: Name of the hospital to find
            
        Returns:
            Hospital URL if found, None otherwise
        """
        if not hospital_name:
            return None
        
        # Try exact match first
        hosp_record = self.mongo_client.hospitals.find_one({"name": hospital_name})
        
        # If not found, try case-insensitive match
        if not hosp_record:
            hosp_record = self.mongo_client.hospitals.find_one({
                "name": {"$regex": f"^{re.escape(hospital_name)}$", "$options": "i"}
            })
        
        # If still not found, try partial match
        if not hosp_record:
            hosp_record = self.mongo_client.hospitals.find_one({
                "$or": [
                    {"name": {"$regex": hospital_name, "$options": "i"}},
                    {"name": {"$regex": f".*{re.escape(hospital_name)}.*", "$options": "i"}}
                ]
            })
        
        if hosp_record:
            return hosp_record.get("url")
        
        return None

    def upsert_hospital_practice(self, practice: dict, doctor: DoctorModel) -> None:
        """Ensure hospital doc exists and record this doctor's practice info for that hospital.

        - Finds hospital by name in the collection (matches by name)
        - Updates hospital with doctor's practice info (fee, timings, location)
        - Merges/updates the hospital's `doctors` list with an entry for this doctor

        Args:
            practice: Dictionary with hospital practice information
            doctor: DoctorModel instance
        """
        if not practice:
            return

        # Skip private practices (video consultations)
        if practice.get("is_private_practice", False):
            return

        hosp_name = practice.get("hospital_name")
        if not hosp_name:
            return

        area = practice.get("area")
        fee = practice.get("fee")
        timings = practice.get("timings") or {}
        lat = practice.get("lat")
        lng = practice.get("lng")
        practice_url = practice.get("practice_url")  # Booking/appointment URL

        # Find hospital by name (case-insensitive, partial match)
        # Try exact match first
        hosp_record = self.mongo_client.hospitals.find_one({"name": hosp_name})
        
        # Find hospital by name (case-insensitive, partial match)
        # Try exact match first
        hosp_record = self.mongo_client.hospitals.find_one({"name": hosp_name})
        
        # If not found, try case-insensitive match
        if not hosp_record:
            hosp_record = self.mongo_client.hospitals.find_one({
                "name": {"$regex": f"^{re.escape(hosp_name)}$", "$options": "i"}
            })
        
        # If still not found, try partial match (hospital name contains or is contained)
        if not hosp_record:
            hosp_record = self.mongo_client.hospitals.find_one({
                "$or": [
                    {"name": {"$regex": hosp_name, "$options": "i"}},
                    {"name": {"$regex": f".*{re.escape(hosp_name)}.*", "$options": "i"}}
                ]
            })

        if not hosp_record:
            logger.warning("Hospital not found in collection: {}", hosp_name)
            return

        hosp_url = hosp_record.get("url")
        if not hosp_url:
            logger.warning("Hospital found but has no URL: {}", hosp_name)
            return

        # Update hospital with new information (area, location, etc.)
        update_fields = {}
        
        # Update area if provided and different
        if area and hosp_record.get("area") != area:
            update_fields["area"] = area
            if not hosp_record.get("address"):
                update_fields["address"] = area
        
        # Update location if provided
        if lat is not None and lng is not None:
            existing_location = hosp_record.get("location")
            if not existing_location or existing_location.get("lat") != lat or existing_location.get("lng") != lng:
                update_fields["location"] = {"lat": lat, "lng": lng}

        # Now merge doctor entry into hospital.doctors
        existing_doctors = hosp_record.get("doctors") or []

        # Doctor entry to upsert into hospital.doctors
        doctor_entry = {
            "profile_url": doctor.profile_url,
            "name": doctor.name,
            "fee": fee,
            "timings": timings,
            "practice_id": practice.get("h_id"),
            "practice_url": practice_url,  # Booking URL
        }

        doctor_updated = False
        for i, d in enumerate(existing_doctors):
            if isinstance(d, dict) and d.get("profile_url") == doctor.profile_url:
                # merge/update fields
                if fee is not None and d.get("fee") != fee:
                    d["fee"] = fee
                    doctor_updated = True
                if timings and d.get("timings") != timings:
                    d["timings"] = timings
                    doctor_updated = True
                if doctor.name and d.get("name") != doctor.name:
                    d["name"] = doctor.name
                    doctor_updated = True
                if practice_url and d.get("practice_url") != practice_url:
                    d["practice_url"] = practice_url
                    doctor_updated = True
                existing_doctors[i] = d
                break
        else:
            # not found, append
            existing_doctors.append(doctor_entry)
            doctor_updated = True

        # Add doctors list to update fields
        if doctor_updated:
            update_fields["doctors"] = existing_doctors

        # Update hospital if there are any changes
        if update_fields:
            try:
                self.mongo_client.hospitals.update_one(
                    {"url": hosp_url},
                    {"$set": update_fields}
                )
                logger.debug("Updated hospital {} with doctor {} info", hosp_name, doctor.name)
            except Exception as exc:
                logger.warning("Failed to update hospital {}: {}", hosp_name, exc)

