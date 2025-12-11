import os
from typing import Optional, Dict
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

class MongoClientManager:
    def __init__(self, test_db: bool = False) -> None:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI missing in .env")
        
        self.client = MongoClient(mongo_uri)
        # Use test database if requested
        db_name = "dr_doctor_test" if test_db else "dr_doctor"
        self.db = self.client[db_name]

        self.doctors = self.db["doctors"]
        self.hospitals = self.db["hospitals"]
        self.cities = self.db["cities"]

        self.doctors.create_index([("profile_url", ASCENDING)], unique=True)
        self.hospitals.create_index([("name", ASCENDING), ("address", ASCENDING)], unique=True)
        self.cities.create_index([("url", ASCENDING)], unique=True)

    # ------------ Doctors -----------------
    def doctor_exists(self, url: str) -> bool:
        return self.doctors.find_one({"profile_url": url}) is not None

    def insert_doctor(self, doc: Dict) -> Optional[str]:
        try:
            result = self.doctors.insert_one(doc)
            return str(result.inserted_id)
        except Exception:
            return None

    def upsert_minimal_doctor(self, profile_url: str, name: str, hospital_url: Optional[str] = None) -> bool:
        """Insert or update a minimal doctor record (just name + profile_url).
        
        Used during Phase 1 to save doctor URLs for later processing.
        If doctor already exists with full data, this won't overwrite it.
        """
        try:
            existing = self.doctors.find_one({"profile_url": profile_url})
            if existing:
                # Doctor already exists, don't overwrite
                return True
            
            # Insert minimal record
            minimal_doc = {
                "profile_url": profile_url,
                "name": name,
                "platform": "marham",  # Will be updated during Phase 2
                "specialty": [],  # Will be populated during Phase 2
                "scrape_status": "pending"  # Track that this needs processing
            }
            self.doctors.insert_one(minimal_doc)
            return True
        except Exception:
            return False

    # ------------ Hospitals -----------------
    def hospital_exists(self, name: str, address: str) -> bool:
        return self.hospitals.find_one({"name": name, "address": address}) is not None

    def insert_hospital(self, doc: Dict) -> Optional[str]:
        try:
            result = self.hospitals.insert_one(doc)
            return str(result.inserted_id)
        except Exception:
            return None

    def close(self) -> None:
        """Close the underlying MongoDB client connection."""
        try:
            if hasattr(self, "client") and self.client:
                self.client.close()
        except Exception:
            pass

    def update_hospital(self, url: Optional[str], doc: Dict) -> bool:
        """Update hospital document by `url` if present, otherwise try name+address.

        Performs an upsert so minimal entries inserted earlier will be enriched.
        Returns True on success, False otherwise.
        """
        try:
            if url:
                result = self.hospitals.update_one({"url": url}, {"$set": doc}, upsert=True)
                return bool(result.raw_result.get("ok", 0))

            # Fallback: try match by name + address
            name = doc.get("name")
            address = doc.get("address")
            if name and address:
                result = self.hospitals.update_one({"name": name, "address": address}, {"$set": doc}, upsert=True)
                return bool(result.raw_result.get("ok", 0))

            return False
        except Exception:
            return False

    def get_hospitals_needing_enrichment(self, limit: Optional[int] = None):
        """Get hospitals that need enrichment (status is 'pending' or missing)."""
        query = {"$or": [{"scrape_status": {"$exists": False}}, {"scrape_status": "pending"}]}
        cursor = self.hospitals.find(query).sort("_id", ASCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return cursor

    def get_hospitals_needing_doctor_collection(self, limit: Optional[int] = None):
        """Get hospitals that need doctor collection (status is 'enriched' but not 'doctors_collected')."""
        query = {"scrape_status": {"$in": ["enriched", "pending"]}}
        cursor = self.hospitals.find(query).sort("_id", ASCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return cursor

    def get_doctors_needing_processing(self, limit: Optional[int] = None):
        """Get doctors that need full processing (status is 'pending' or missing)."""
        query = {"$or": [
            {"scrape_status": {"$exists": False}},
            {"scrape_status": "pending"},
            {"specialty": {"$exists": False}},
            {"specialty": []}
        ]}
        cursor = self.doctors.find(query).sort("_id", ASCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return cursor

    def update_doctor_status(self, profile_url: str, status: str) -> bool:
        """Update doctor's scrape status."""
        try:
            self.doctors.update_one(
                {"profile_url": profile_url},
                {"$set": {"scrape_status": status}}
            )
            return True
        except Exception:
            return False

    def update_hospital_status(self, url: str, status: str) -> bool:
        """Update hospital's scrape status."""
        try:
            self.hospitals.update_one(
                {"url": url},
                {"$set": {"scrape_status": status}}
            )
            return True
        except Exception:
            return False

    # ------------ Cities -----------------
    def city_exists(self, url: str) -> bool:
        """Check if city exists by URL."""
        return self.cities.find_one({"url": url}) is not None

    def upsert_city(self, name: str, url: str) -> bool:
        """Insert or update a city record.
        
        Args:
            name: City name
            url: City URL (format: https://www.marham.pk/hospitals/{city})
            
        Returns:
            True on success, False otherwise
        """
        try:
            from datetime import datetime
            self.cities.update_one(
                {"url": url},
                {
                    "$set": {
                        "name": name,
                        "url": url,
                        "platform": "marham",
                    },
                    "$setOnInsert": {
                        "scrape_status": "pending",
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception:
            return False

    def get_cities_needing_scraping(self, limit: Optional[int] = None):
        """Get cities that need scraping (status is 'pending' or missing)."""
        query = {"$or": [
            {"scrape_status": {"$exists": False}},
            {"scrape_status": "pending"}
        ]}
        cursor = self.cities.find(query).sort("_id", ASCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return cursor

    def update_city_status(self, url: str, status: str) -> bool:
        """Update city's scrape status."""
        try:
            from datetime import datetime
            self.cities.update_one(
                {"url": url},
                {
                    "$set": {
                        "scrape_status": status,
                        "scraped_at": datetime.utcnow() if status == "scraped" else None
                    }
                }
            )
            return True
        except Exception:
            return False
