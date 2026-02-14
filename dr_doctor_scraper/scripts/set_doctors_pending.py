"""Set all doctors' scrape_status to 'pending'."""

import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def set_all_doctors_pending(test_db: bool = False):
    """Set all doctors' scrape_status to 'pending'.
    
    Args:
        test_db: If True, update test database, else production database
    """
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("ERROR: MONGO_URI not found in .env")
        return
    
    client = MongoClient(mongo_uri)
    db_name = "dr_doctor_test" if test_db else "dr_doctor"
    db = client[db_name]
    doctors_collection = db["doctors"]
    
    print("=" * 80)
    print(f"SETTING ALL DOCTORS TO PENDING - {db_name.upper()}")
    print("=" * 80)
    print()
    
    # Count total doctors
    total_doctors = doctors_collection.count_documents({})
    print(f"Total doctors in database: {total_doctors}")
    print()
    
    if total_doctors == 0:
        print("No doctors found in database.")
        client.close()
        return
    
    # Update all doctors to pending
    result = doctors_collection.update_many(
        {},
        {"$set": {"scrape_status": "pending"}}
    )
    
    print(f"[OK] Updated {result.modified_count} doctors to 'pending' status")
    print(f"   Matched: {result.matched_count} doctors")
    print()
    
    # Verify the update
    pending_count = doctors_collection.count_documents({"scrape_status": "pending"})
    processed_count = doctors_collection.count_documents({"scrape_status": "processed"})
    other_count = total_doctors - pending_count - processed_count
    
    print("Status breakdown:")
    print(f"   Pending: {pending_count}")
    print(f"   Processed: {processed_count}")
    print(f"   Other: {other_count}")
    print()
    
    if pending_count == total_doctors:
        print("[OK] All doctors are now set to 'pending'!")
    else:
        print(f"[WARN] Not all doctors are pending. {total_doctors - pending_count} doctors have other statuses.")
    
    client.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Set all doctors' scrape_status to 'pending'")
    parser.add_argument("--test-db", action="store_true", help="Update test database instead of production")
    args = parser.parse_args()
    
    db_name = "dr_doctor_test" if args.test_db else "dr_doctor"
    
    response = input(f"Set all doctors to 'pending' in '{db_name}' database? (yes/no): ")
    if response.lower() != "yes":
        print("Operation cancelled")
        sys.exit(0)
    
    set_all_doctors_pending(test_db=args.test_db)

