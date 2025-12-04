import os
from typing import Optional, Dict
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

class MongoClientManager:
    def __init__(self) -> None:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError(
                "MONGO_URI missing in .env file. "
                "Please set MONGO_URI in your .env file (e.g., MONGO_URI=mongodb://localhost:27017/). "
                "Make sure MongoDB is running before starting the scraper."
            )
        
        try:
            self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command("ping")
        except Exception as e:
            error_msg = (
                f"Failed to connect to MongoDB at {mongo_uri}\n"
                f"Error: {str(e)}\n\n"
                "Troubleshooting:\n"
                "1. Make sure MongoDB is running (check with: mongosh or mongo)\n"
                "2. Verify MONGO_URI in .env file is correct\n"
                "3. Check if MongoDB is listening on the expected port\n"
                "4. For local MongoDB: Start it with 'mongod' or check Windows Services"
            )
            raise ConnectionError(error_msg) from e
        
        self.db = self.client["dr_doctor"]

        self.doctors = self.db["doctors"]
        self.hospitals = self.db["hospitals"]

        self.doctors.create_index([("profile_url", ASCENDING)], unique=True)
        self.hospitals.create_index([("name", ASCENDING), ("address", ASCENDING)], unique=True)

    # ------------ Doctors -----------------
    def doctor_exists(self, url: str) -> bool:
        return self.doctors.find_one({"profile_url": url}) is not None

    def insert_doctor(self, doc: Dict) -> Optional[str]:
        try:
            result = self.doctors.insert_one(doc)
            return str(result.inserted_id)
        except Exception:
            return None

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
