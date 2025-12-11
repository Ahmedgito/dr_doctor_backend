
"""Export current database to JSON and optionally clear it for review."""

from __future__ import annotations

import sys
import pathlib
import json
from datetime import datetime

root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from scrapers.database.mongo_client import MongoClientManager
from scrapers.logger import logger


def normalize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable format."""
    out = {}
    for k, v in doc.items():
        if k == "_id":
            out[k] = str(v)
            continue
        try:
            json.dumps({k: v})
            out[k] = v
        except TypeError:
            out[k] = str(v)
    return out


def export_and_clear_db(clear: bool = False) -> None:
    """Export all collections to JSON and optionally clear the database."""
    mongo = MongoClientManager()
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export doctors
        doctors = list(mongo.doctors.find({}))
        doctors_file = f"data/exports/doctors_backup_{timestamp}.json"
        pathlib.Path("data/exports").mkdir(parents=True, exist_ok=True)
        
        with open(doctors_file, "w", encoding="utf-8") as f:
            json.dump([normalize_doc(d) for d in doctors], f, indent=2, ensure_ascii=False)
        
        logger.info("Exported {} doctors to {}", len(doctors), doctors_file)
        
        # Export hospitals
        hospitals = list(mongo.hospitals.find({}))
        hospitals_file = f"data/exports/hospitals_backup_{timestamp}.json"
        
        with open(hospitals_file, "w", encoding="utf-8") as f:
            json.dump([normalize_doc(h) for h in hospitals], f, indent=2, ensure_ascii=False)
        
        logger.info("Exported {} hospitals to {}", len(hospitals), hospitals_file)
        
        # Export cities
        cities = list(mongo.cities.find({}))
        cities_file = f"data/exports/cities_backup_{timestamp}.json"
        
        with open(cities_file, "w", encoding="utf-8") as f:
            json.dump([normalize_doc(c) for c in cities], f, indent=2, ensure_ascii=False)
        
        logger.info("Exported {} cities to {}", len(cities), cities_file)
        
        if clear:
            # Clear collections
            mongo.doctors.delete_many({})
            mongo.hospitals.delete_many({})
            mongo.cities.delete_many({})
            logger.info("Cleared all data from database (doctors, hospitals, cities)")
        else:
            logger.info("Database not cleared. Use --clear flag to clear after export.")
        
        print(f"\n✅ Export complete!")
        print(f"   Doctors: {len(doctors)} → {doctors_file}")
        print(f"   Hospitals: {len(hospitals)} → {hospitals_file}")
        print(f"   Cities: {len(cities)} → {cities_file}")
        if clear:
            print(f"   Database cleared (doctors, hospitals, cities)")
        
    finally:
        mongo.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export DB to JSON and optionally clear it")
    parser.add_argument("--clear", action="store_true", help="Clear database after export")
    args = parser.parse_args()
    
    export_and_clear_db(clear=args.clear)

