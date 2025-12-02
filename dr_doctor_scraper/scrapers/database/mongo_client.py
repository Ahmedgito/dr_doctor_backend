from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from loguru import logger
from pymongo import MongoClient, errors


load_dotenv()


class MongoClientManager:
    """MongoDB client wrapper for doctor documents."""

    def __init__(
        self,
        uri_env: str = "MONGO_URI",
        db_name: str = "dr_doctor",
        collection_name: str = "doctors",
    ) -> None:
        uri = os.getenv(uri_env)
        if not uri:
            raise RuntimeError(f"Environment variable {uri_env} is not set.")

        logger.info("Connecting to MongoDB at {}", uri)
        try:
            self.client = MongoClient(uri)
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            self._ensure_indexes()
        except errors.PyMongoError as exc:  # noqa: BLE001
            logger.exception("Failed to connect to MongoDB: {}", exc)
            raise

    def _ensure_indexes(self) -> None:
        """Create indexes for faster lookups and uniqueness."""

        logger.debug("Ensuring MongoDB indexes on 'profile_url' and 'platform'")
        self.collection.create_index("profile_url", unique=True)
        self.collection.create_index("platform")

    # --- helper methods -----------------------------------------------------------

    def doctor_exists(self, profile_url: str) -> bool:
        return self.collection.count_documents({"profile_url": profile_url}, limit=1) > 0

    def insert_doctor(self, doc: Dict[str, Any]) -> Optional[str]:
        """Insert a new doctor document.

        Returns inserted_id as string or None if duplicate / failure.
        """

        if "scraped_at" not in doc:
            doc["scraped_at"] = datetime.utcnow()

        try:
            result = self.collection.insert_one(doc)
            logger.info("Inserted doctor: {} (id={})", doc.get("name"), result.inserted_id)
            return str(result.inserted_id)
        except errors.DuplicateKeyError:
            logger.info("Duplicate doctor skipped (profile_url={})", doc.get("profile_url"))
            return None
        except errors.PyMongoError as exc:  # noqa: BLE001
            logger.exception("Failed to insert doctor {}: {}", doc.get("name"), exc)
            return None

    def update_doctor(self, doc: Dict[str, Any]) -> bool:
        """Upsert doctor document by profile_url."""

        if "profile_url" not in doc:
            raise ValueError("Doctor document must include 'profile_url' for update.")

        if "scraped_at" not in doc:
            doc["scraped_at"] = datetime.utcnow()

        try:
            result = self.collection.update_one(
                {"profile_url": doc["profile_url"]},
                {"$set": doc},
                upsert=True,
            )
            logger.info(
                "Upserted doctor: {} (matched={}, modified={}, upserted_id={})",
                doc.get("name"),
                result.matched_count,
                result.modified_count,
                result.upserted_id,
            )
            return True
        except errors.PyMongoError as exc:  # noqa: BLE001
            logger.exception("Failed to update doctor {}: {}", doc.get("name"), exc)
            return False

    def close(self) -> None:
        try:
            self.client.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error while closing Mongo client: {}", exc)
