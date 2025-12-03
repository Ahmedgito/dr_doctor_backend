import os
from typing import Optional, Dict
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

class MongoClientManager:
    def __init__(self) -> None:
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            raise ValueError("MONGO_URI missing in .env")
        
        self.client = MongoClient(mongo_uri)
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
