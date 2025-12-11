"""Clear all collections from the database."""

from __future__ import annotations

import sys
import pathlib

root = pathlib.Path(__file__).resolve().parents[1]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from scrapers.logger import logger


def clear_database(test_db: bool = False) -> None:
    """Clear all collections from the database."""
    from pymongo import MongoClient
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI missing in .env")
    
    client = MongoClient(mongo_uri)
    db_name = "dr_doctor_test" if test_db else "dr_doctor"
    db = client[db_name]
    
    try:
        logger.warning("⚠️  CLEARING DATABASE: {}", db_name)
        
        # Get counts before clearing
        doctors_count = db["doctors"].count_documents({})
        hospitals_count = db["hospitals"].count_documents({})
        cities_count = db["cities"].count_documents({})
        pages_count = db["pages"].count_documents({})
        
        # Drop all indexes first (to avoid duplicate key errors)
        logger.info("Dropping existing indexes...")
        try:
            db["doctors"].drop_indexes()
            db["hospitals"].drop_indexes()
            db["cities"].drop_indexes()
            db["pages"].drop_indexes()
            logger.info("Indexes dropped successfully")
        except Exception as exc:
            logger.warning("Error dropping indexes (may not exist): {}", exc)
        
        # Clear collections
        logger.info("Clearing collections...")
        db["doctors"].delete_many({})
        db["hospitals"].delete_many({})
        db["cities"].delete_many({})
        db["pages"].delete_many({})
        
        logger.info("✅ Database cleared successfully")
        logger.info("   Deleted: {} doctors, {} hospitals, {} cities, {} pages", doctors_count, hospitals_count, cities_count, pages_count)
        
        print(f"\n✅ Database '{db_name}' cleared successfully!")
        print(f"   Deleted: {doctors_count} doctors, {hospitals_count} hospitals, {cities_count} cities, {pages_count} pages")
        print(f"   Indexes dropped - will be recreated on next scraper run")
        
    finally:
        client.close()


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

