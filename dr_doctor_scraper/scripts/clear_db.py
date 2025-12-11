"""Clear all collections from the database."""

from __future__ import annotations

import sys
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from scrapers.database.mongo_client import MongoClientManager
from scrapers.logger import logger


def clear_database(test_db: bool = False) -> None:
    """Clear all collections from the database."""
    mongo = MongoClientManager(test_db=test_db)
    
    try:
        db_name = "dr_doctor_test" if test_db else "dr_doctor"
        logger.warning("⚠️  CLEARING DATABASE: {}", db_name)
        
        # Get counts before clearing
        doctors_count = mongo.doctors.count_documents({})
        hospitals_count = mongo.hospitals.count_documents({})
        cities_count = mongo.cities.count_documents({})
        
        # Clear collections
        mongo.doctors.delete_many({})
        mongo.hospitals.delete_many({})
        mongo.cities.delete_many({})
        
        logger.info("✅ Database cleared successfully")
        logger.info("   Deleted: {} doctors, {} hospitals, {} cities", doctors_count, hospitals_count, cities_count)
        
        print(f"\n✅ Database '{db_name}' cleared successfully!")
        print(f"   Deleted: {doctors_count} doctors, {hospitals_count} hospitals, {cities_count} cities")
        
    finally:
        mongo.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clear all collections from database")
    parser.add_argument("--test-db", action="store_true", help="Clear test database instead of production")
    args = parser.parse_args()
    
    # Confirm before clearing
    db_name = "dr_doctor_test" if args.test_db else "dr_doctor"
    response = input(f"⚠️  WARNING: This will DELETE ALL DATA from '{db_name}' database!\nType 'yes' to confirm: ")
    
    if response.lower() == "yes":
        clear_database(test_db=args.test_db)
    else:
        print("❌ Operation cancelled")

