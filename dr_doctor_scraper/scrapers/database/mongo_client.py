import os
from typing import Optional, Dict, List
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv
from scrapers.logger import logger

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
        self.pages = self.db["pages"]

        # Create indexes (drop existing first if they have duplicates)
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes, handling duplicate key errors by dropping and recreating."""
        try:
            # Doctors: unique index on profile_url
            try:
                self.doctors.create_index([("profile_url", ASCENDING)], unique=True)
            except Exception as exc:
                if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                    logger.warning("Duplicate keys found in doctors, dropping and recreating index...")
                    try:
                        self.doctors.drop_index("profile_url_1")
                    except Exception:
                        pass
                    # Remove duplicates before creating index
                    self._remove_duplicate_doctors()
                    self.doctors.create_index([("profile_url", ASCENDING)], unique=True)
                else:
                    raise
            
            # Hospitals: unique index on url
            try:
                self.hospitals.create_index([("url", ASCENDING)], unique=True)
            except Exception as exc:
                if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                    logger.warning("Duplicate keys found in hospitals, dropping and recreating index...")
                    try:
                        self.hospitals.drop_index("url_1")
                    except Exception:
                        pass
                    # Remove duplicates before creating index
                    self._remove_duplicate_hospitals()
                    self.hospitals.create_index([("url", ASCENDING)], unique=True)
                else:
                    raise
            
            # Hospitals: non-unique index on name+address for queries
            try:
                self.hospitals.create_index([("name", ASCENDING), ("address", ASCENDING)])
            except Exception:
                pass  # Non-unique, can fail silently
            
            # Cities: unique index on url
            try:
                self.cities.create_index([("url", ASCENDING)], unique=True)
            except Exception as exc:
                if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                    logger.warning("Duplicate keys found in cities, dropping and recreating index...")
                    try:
                        self.cities.drop_index("url_1")
                    except Exception:
                        pass
                    # Remove duplicates before creating index
                    self._remove_duplicate_cities()
                    self.cities.create_index([("url", ASCENDING)], unique=True)
                else:
                    raise
            
            # Pages: unique index on url
            try:
                self.pages.create_index([("url", ASCENDING)], unique=True)
            except Exception as exc:
                if "duplicate key" in str(exc).lower() or "E11000" in str(exc):
                    logger.warning("Duplicate keys found in pages, dropping and recreating index...")
                    try:
                        self.pages.drop_index("url_1")
                    except Exception:
                        pass
                    self.pages.create_index([("url", ASCENDING)], unique=True)
                else:
                    raise
            
            # Pages: index on status for queries
            try:
                self.pages.create_index([("scrape_status", ASCENDING)])
            except Exception:
                pass
        except Exception as exc:
            logger.error("Failed to create indexes: {}", exc)
            # Continue anyway - indexes are not critical for basic operations

    def _remove_duplicate_doctors(self) -> None:
        """Remove duplicate doctors keeping the first one."""
        pipeline = [
            {"$group": {
                "_id": "$profile_url",
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        duplicates = list(self.doctors.aggregate(pipeline))
        for dup in duplicates:
            ids = dup["ids"]
            # Keep the first one, delete the rest
            if len(ids) > 1:
                self.doctors.delete_many({"_id": {"$in": ids[1:]}})
                logger.info("Removed {} duplicate doctors with profile_url: {}", len(ids) - 1, dup["_id"])

    def _remove_duplicate_hospitals(self) -> None:
        """Remove duplicate hospitals keeping the first one."""
        from pymongo import ASCENDING
        pipeline = [
            {"$group": {
                "_id": "$url",
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        duplicates = list(self.hospitals.aggregate(pipeline))
        for dup in duplicates:
            ids = dup["ids"]
            # Keep the first one, delete the rest
            if len(ids) > 1:
                self.hospitals.delete_many({"_id": {"$in": ids[1:]}})
                logger.info("Removed {} duplicate hospitals with URL: {}", len(ids) - 1, dup["_id"])

    def _remove_duplicate_cities(self) -> None:
        """Remove duplicate cities keeping the first one."""
        pipeline = [
            {"$group": {
                "_id": "$url",
                "ids": {"$push": "$_id"},
                "count": {"$sum": 1}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        duplicates = list(self.cities.aggregate(pipeline))
        for dup in duplicates:
            ids = dup["ids"]
            # Keep the first one, delete the rest
            if len(ids) > 1:
                self.cities.delete_many({"_id": {"$in": ids[1:]}})
                logger.info("Removed {} duplicate cities with URL: {}", len(ids) - 1, dup["_id"])

    # ------------ Pages -----------------
    def upsert_page(self, url: str, city_name: Optional[str] = None, city_url: Optional[str] = None, page_number: Optional[int] = None) -> bool:
        """Insert or update a page record.
        
        Args:
            url: Full page URL
            city_name: City name for reference
            city_url: City URL for reference
            page_number: Page number
            
        Returns:
            True on success, False otherwise
        """
        try:
            from datetime import datetime
            self.pages.update_one(
                {"url": url},
                {
                    "$set": {
                        "url": url,
                        "city_name": city_name,
                        "city_url": city_url,
                        "page_number": page_number,
                        "platform": "marham",
                    },
                    "$setOnInsert": {
                        "scrape_status": "pending",
                        "retry_count": 0,
                        "created_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return True
        except Exception as exc:
            logger.warning("Failed to upsert page {}: {}", url, exc)
            return False

    def mark_page_success(self, url: str) -> bool:
        """Mark a page as successfully scraped."""
        try:
            from datetime import datetime
            self.pages.update_one(
                {"url": url},
                {
                    "$set": {
                        "scrape_status": "success",
                        "scraped_at": datetime.utcnow(),
                        "last_attempt": datetime.utcnow()
                    }
                }
            )
            return True
        except Exception:
            return False

    def mark_page_failed(self, url: str, error_message: Optional[str] = None) -> bool:
        """Mark a page as failed and increment retry count."""
        try:
            from datetime import datetime
            self.pages.update_one(
                {"url": url},
                {
                    "$set": {
                        "scrape_status": "failed",
                        "error_message": error_message,
                        "last_attempt": datetime.utcnow()
                    },
                    "$inc": {"retry_count": 1}
                }
            )
            return True
        except Exception:
            return False

    def mark_page_retrying(self, url: str) -> bool:
        """Mark a page as being retried."""
        try:
            from datetime import datetime
            self.pages.update_one(
                {"url": url},
                {
                    "$set": {
                        "scrape_status": "retrying",
                        "last_attempt": datetime.utcnow()
                    }
                }
            )
            return True
        except Exception:
            return False

    def get_pages_needing_retry(self, limit: Optional[int] = None, max_retries: int = 5) -> List[dict]:
        """Get pages that need to be retried (status is 'failed' or 'pending').
        
        Args:
            limit: Maximum number to return
            max_retries: Maximum retry count (pages with more retries are excluded)
            
        Returns:
            List of page documents
        """
        query = {
            "$or": [
                {"scrape_status": "pending"},
                {"scrape_status": "failed"},
                {"scrape_status": "retrying"}
            ],
            "retry_count": {"$lt": max_retries}
        }
        cursor = self.pages.find(query).sort("_id", ASCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    # ------------ Doctors -----------------
    def doctor_exists(self, url: str) -> bool:
        return self.doctors.find_one({"profile_url": url}) is not None

    def insert_doctor(self, doc: Dict) -> Optional[str]:
        """Insert doctor using upsert to prevent duplicates.
        
        Uses profile_url as unique identifier. If doctor exists, updates it.
        Returns inserted/updated document ID or None on failure.
        """
        try:
            profile_url = doc.get("profile_url")
            if not profile_url:
                logger.warning("Cannot insert doctor without profile_url")
                return None
            
            # Use upsert to prevent duplicates
            result = self.doctors.update_one(
                {"profile_url": profile_url},
                {"$set": doc},
                upsert=True
            )
            if result.upserted_id:
                return str(result.upserted_id)
            # If updated, get the existing document ID
            existing = self.doctors.find_one({"profile_url": profile_url})
            return str(existing["_id"]) if existing else None
        except Exception as exc:
            logger.warning("Failed to insert/update doctor {}: {}", doc.get("profile_url"), exc)
            return None

    def upsert_minimal_doctor(self, profile_url: str, name: str, hospital_url: Optional[str] = None) -> bool:
        """Insert or update a minimal doctor record (just name + profile_url).
        
        Used during Step 2 to save doctor URLs for later processing.
        If doctor already exists with full data, this won't overwrite it.
        Only sets minimal fields if doctor doesn't exist.
        """
        try:
            existing = self.doctors.find_one({"profile_url": profile_url})
            if existing:
                # Doctor already exists - don't overwrite existing data
                # Only update scrape_status if it's missing or still "pending"
                if existing.get("scrape_status") not in ["processed", "enriched"]:
                    self.doctors.update_one(
                        {"profile_url": profile_url},
                        {"$set": {"scrape_status": "pending"}}
                    )
                return True
            
            # Insert minimal record only if doctor doesn't exist
            minimal_doc = {
                "profile_url": profile_url,
                "name": name,
                "platform": "marham",
                "specialty": [],  # Will be populated during Step 3
                "scrape_status": "pending"  # Track that this needs processing
            }
            self.doctors.insert_one(minimal_doc)
            return True
        except Exception as exc:
            # Handle duplicate key errors (shouldn't happen with proper check)
            logger.warning("Failed to upsert minimal doctor {}: {}", profile_url, exc)
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
        """Update hospital document by `url` (primary method).

        Performs an upsert so minimal entries inserted earlier will be enriched.
        URL is the unique identifier to prevent duplicates.
        Returns True on success, False otherwise.
        """
        try:
            # URL is required for proper deduplication
            hospital_url = url or doc.get("url")
            if not hospital_url:
                logger.warning("Cannot update hospital without URL: {}", doc.get("name"))
                return False
            
            # Use URL as the unique identifier (prevents duplicates)
            result = self.hospitals.update_one(
                {"url": hospital_url}, 
                {"$set": doc}, 
                upsert=True
            )
            return bool(result.raw_result.get("ok", 0))
        except Exception as exc:
            # Handle duplicate key errors gracefully
            logger.warning("Failed to update hospital {}: {}", doc.get("name"), exc)
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
