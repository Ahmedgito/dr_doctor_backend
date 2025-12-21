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
        
        # Crawler collections
        self.crawled_pages = self.db["crawled_pages"]
        self.site_maps = self.db["site_maps"]
        self.crawled_assets = self.db["crawled_assets"]
        self.crawl_queue = self.db["crawl_queue"]
        self.crawl_locks = self.db["crawl_locks"]
        self.crawl_jobs = self.db["crawl_jobs"]

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
            
            # Crawled pages: unique index on url
            try:
                self.crawled_pages.create_index([("url", ASCENDING)], unique=True)
            except Exception:
                pass
            
            # Crawled pages: indexes for queries
            try:
                self.crawled_pages.create_index([("domain", ASCENDING)])
                self.crawled_pages.create_index([("crawl_status", ASCENDING)])
                self.crawled_pages.create_index([("depth", ASCENDING)])
            except Exception:
                pass
            
            # Site maps: unique index on domain
            try:
                self.site_maps.create_index([("domain", ASCENDING)], unique=True)
            except Exception:
                pass
            
            # Crawled assets: indexes
            try:
                self.crawled_assets.create_index([("url", ASCENDING)])
                self.crawled_assets.create_index([("parent_url", ASCENDING)])
                self.crawled_assets.create_index([("domain", ASCENDING)])
            except Exception:
                pass
            
            # Crawl queue: indexes for distributed crawling
            try:
                self.crawl_queue.create_index([("url", ASCENDING)], unique=True)
                self.crawl_queue.create_index([("status", ASCENDING)])
                self.crawl_queue.create_index([("domain", ASCENDING)])
            except Exception:
                pass
        except Exception as exc:
            logger.error("Failed to create indexes: {}", exc)
            # Continue anyway - indexes are not critical for basic operations

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
    
    # ------------ Crawler Methods -----------------
    def upsert_crawled_page(self, page_data: Dict) -> bool:
        """Insert or update a crawled page.
        
        Args:
            page_data: Dictionary with page data (must include 'url')
            
        Returns:
            True on success, False otherwise
        """
        try:
            url = page_data.get("url")
            if not url:
                logger.warning("Cannot upsert crawled page without URL")
                return False
            
            self.crawled_pages.update_one(
                {"url": url},
                {"$set": page_data},
                upsert=True
            )
            return True
        except Exception as exc:
            logger.warning("Failed to upsert crawled page {}: {}", page_data.get("url"), exc)
            return False
    
    def get_crawled_pages(self, domain: str, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict]:
        """Get crawled pages for a domain.
        
        Args:
            domain: Domain name
            status: Optional status filter ("pending", "crawled", "failed")
            limit: Optional limit on number of results
            
        Returns:
            List of crawled page documents
        """
        query = {"domain": domain}
        if status:
            query["crawl_status"] = status
        
        cursor = self.crawled_pages.find(query).sort("_id", ASCENDING)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)
    
    def get_pages_with_keywords(self, keywords: List[str], domain: Optional[str] = None) -> List[Dict]:
        """Get pages that contain any of the specified keywords.
        
        Args:
            keywords: List of keywords to search for
            domain: Optional domain filter
            
        Returns:
            List of crawled page documents
        """
        query = {"keywords_found": {"$in": keywords}}
        if domain:
            query["domain"] = domain
        
        return list(self.crawled_pages.find(query))
    
    def get_site_map(self, domain: str) -> Optional[Dict]:
        """Get site map for a domain.
        
        Args:
            domain: Domain name
            
        Returns:
            Site map document or None
        """
        return self.site_maps.find_one({"domain": domain})
    
    def upsert_site_map(self, site_map_data: Dict) -> bool:
        """Insert or update site map.
        
        Args:
            site_map_data: Dictionary with site map data (must include 'domain')
            
        Returns:
            True on success, False otherwise
        """
        try:
            domain = site_map_data.get("domain")
            if not domain:
                logger.warning("Cannot upsert site map without domain")
                return False
            
            from datetime import datetime
            site_map_data["updated_at"] = datetime.utcnow()
            
            self.site_maps.update_one(
                {"domain": domain},
                {"$set": site_map_data},
                upsert=True
            )
            return True
        except Exception as exc:
            logger.warning("Failed to upsert site map for domain {}: {}", site_map_data.get("domain"), exc)
            return False
    
    def mark_page_crawled(self, url: str) -> bool:
        """Mark a page as crawled.
        
        Args:
            url: URL of the page
            
        Returns:
            True on success, False otherwise
        """
        try:
            from datetime import datetime
            self.crawled_pages.update_one(
                {"url": url},
                {
                    "$set": {
                        "crawl_status": "crawled",
                        "crawled_at": datetime.utcnow()
                    }
                }
            )
            return True
        except Exception:
            return False
    
    def mark_page_failed(self, url: str, error: str) -> bool:
        """Mark a page as failed.
        
        Args:
            url: URL of the page
            error: Error message
            
        Returns:
            True on success, False otherwise
        """
        try:
            self.crawled_pages.update_one(
                {"url": url},
                {
                    "$set": {
                        "crawl_status": "failed",
                        "error_message": error
                    }
                }
            )
            return True
        except Exception:
            return False
    
    def page_crawled(self, url: str) -> bool:
        """Check if a page has been crawled.
        
        Args:
            url: URL to check
            
        Returns:
            True if page exists and is crawled
        """
        page = self.crawled_pages.find_one({"url": url})
        return page is not None and page.get("crawl_status") == "crawled"
    
    def upsert_crawled_asset(self, asset_data: Dict) -> bool:
        """Insert or update a crawled asset.
        
        Args:
            asset_data: Dictionary with asset data (must include 'url')
            
        Returns:
            True on success, False otherwise
        """
        try:
            url = asset_data.get("url")
            if not url:
                return False
            
            self.crawled_assets.update_one(
                {"url": url, "parent_url": asset_data.get("parent_url")},
                {"$set": asset_data},
                upsert=True
            )
            return True
        except Exception as exc:
            logger.debug("Failed to upsert asset {}: {}", asset_data.get("url"), exc)
            return False
    
    def bulk_upsert_crawled_assets(self, assets: List[Dict]) -> int:
        """Bulk upsert crawled assets.
        
        Args:
            assets: List of asset dictionaries
            
        Returns:
            Number of assets inserted/updated
        """
        if not assets:
            return 0
        
        try:
            from pymongo import UpdateOne
            operations = []
            
            for asset in assets:
                url = asset.get("url")
                parent_url = asset.get("parent_url")
                if url and parent_url:
                    operations.append(
                        UpdateOne(
                            {"url": url, "parent_url": parent_url},
                            {"$set": asset},
                            upsert=True
                        )
                    )
            
            if operations:
                result = self.crawled_assets.bulk_write(operations)
                return result.modified_count + result.upserted_count
            return 0
        except Exception as exc:
            logger.warning("Failed to bulk upsert assets: {}", exc)
            return 0
