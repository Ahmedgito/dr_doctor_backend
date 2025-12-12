"""Test script to verify doctor-hospital relationships with a small sample."""

import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def clear_test_db():
    """Clear test database without confirmation."""
    import os
    from pymongo import MongoClient
    from dotenv import load_dotenv
    
    load_dotenv()
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI missing in .env")
    
    client = MongoClient(mongo_uri)
    db = client["dr_doctor_test"]
    
    print("Clearing test database...")
    
    # Drop all indexes first
    try:
        db["doctors"].drop_indexes()
        db["hospitals"].drop_indexes()
        db["cities"].drop_indexes()
        db["pages"].drop_indexes()
    except Exception:
        pass
    
    # Clear collections
    doctors_count = db["doctors"].count_documents({})
    hospitals_count = db["hospitals"].count_documents({})
    cities_count = db["cities"].count_documents({})
    pages_count = db["pages"].count_documents({})
    
    db["doctors"].delete_many({})
    db["hospitals"].delete_many({})
    db["cities"].delete_many({})
    db["pages"].delete_many({})
    
    print(f"[OK] Test database cleared: {doctors_count} doctors, {hospitals_count} hospitals, {cities_count} cities, {pages_count} pages\n")
    client.close()

def run_sample_scraper():
    """Run scraper with limit of 5 hospitals."""
    print("=" * 80)
    print("RUNNING SAMPLE SCRAPER (5 hospitals)")
    print("=" * 80)
    
    from scrapers.database.mongo_client import MongoClientManager
    from scrapers.marham.multi_threaded_scraper import MultiThreadedMarhamScraper
    
    mongo = MongoClientManager(test_db=True)
    
    try:
        scraper = MultiThreadedMarhamScraper(
            mongo_client=mongo,
            num_threads=2,  # Use 2 threads for faster processing
            headless=True,
        )
        
        # Run all steps with limit
        # Note: limit applies to hospitals collected in Step 1
        print("Running Step 0: Collect cities...")
        scraper.scrape(limit=None, step=0)
        
        print("\nRunning Step 1: Collect hospitals (limit 5)...")
        scraper.scrape(limit=5, step=1)  # Limit to 5 hospitals
        
        print("\nRunning Step 2: Enrich hospitals and collect doctors...")
        scraper.scrape(limit=None, step=2)  # Process all hospitals from Step 1
        
        print("\nRunning Step 3: Process doctor profiles...")
        scraper.scrape(limit=None, step=3)  # Process all doctors from Step 2
        
        print("\n[OK] Scraping completed\n")
        
    finally:
        mongo.close()

def verify_relationships():
    """Verify doctor-hospital relationships."""
    print("=" * 80)
    print("VERIFYING RELATIONSHIPS")
    print("=" * 80)
    
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("ERROR: MONGO_URI not found in .env")
        return False
    
    client = MongoClient(mongo_uri)
    db = client["dr_doctor_test"]
    
    doctors_collection = db["doctors"]
    hospitals_collection = db["hospitals"]
    
    # Count totals
    total_doctors = doctors_collection.count_documents({})
    total_hospitals = hospitals_collection.count_documents({})
    
    print(f"Total Doctors: {total_doctors}")
    print(f"Total Hospitals: {total_hospitals}")
    print()
    
    # Check doctors with hospitals
    doctors_with_hospitals = doctors_collection.count_documents({
        "hospitals": {"$exists": True, "$ne": None, "$ne": []}
    })
    
    # Check hospitals with doctors
    hospitals_with_doctors = hospitals_collection.count_documents({
        "doctors": {"$exists": True, "$ne": None, "$ne": []}
    })
    
    print(f"Doctors WITH hospitals list: {doctors_with_hospitals}/{total_doctors}")
    print(f"Hospitals WITH doctors list: {hospitals_with_doctors}/{total_hospitals}")
    print()
    
    # Check bidirectional relationships
    verified_bidirectional = 0
    missing_reverse = 0
    
    doctors_with_hospitals_list = list(doctors_collection.find(
        {"hospitals": {"$exists": True, "$ne": None, "$ne": []}},
        {"name": 1, "profile_url": 1, "hospitals": 1}
    ).limit(100))
    
    for doctor in doctors_with_hospitals_list:
        doctor_url = doctor.get("profile_url")
        hospitals = doctor.get("hospitals", [])
        
        for hosp_entry in hospitals:
            if isinstance(hosp_entry, dict):
                hosp_url = hosp_entry.get("url")
                if hosp_url:
                    hospital = hospitals_collection.find_one({"url": hosp_url})
                    if hospital:
                        doctors_list = hospital.get("doctors", [])
                        found = False
                        for doc_entry in doctors_list:
                            if isinstance(doc_entry, dict) and doc_entry.get("profile_url") == doctor_url:
                                found = True
                                break
                        
                        if found:
                            verified_bidirectional += 1
                        else:
                            missing_reverse += 1
    
    print(f"Verified bidirectional relationships: {verified_bidirectional}")
    print(f"Missing reverse relationships: {missing_reverse}")
    print()
    
    # Determine if relationships are established
    relationships_established = (
        doctors_with_hospitals > 0 and 
        hospitals_with_doctors > 0 and 
        missing_reverse == 0
    )
    
    if relationships_established:
        print("[OK] RELATIONSHIPS ESTABLISHED!")
        print(f"   - {doctors_with_hospitals} doctors have hospitals")
        print(f"   - {hospitals_with_doctors} hospitals have doctors")
        print(f"   - All relationships are bidirectional")
    else:
        print("[ERROR] RELATIONSHIPS NOT FULLY ESTABLISHED")
        if doctors_with_hospitals == 0:
            print("   - No doctors have hospitals list")
        if hospitals_with_doctors == 0:
            print("   - No hospitals have doctors list")
        if missing_reverse > 0:
            print(f"   - {missing_reverse} relationships are not bidirectional")
    
    client.close()
    return relationships_established

def set_doctors_to_pending():
    """Set all doctors' scrape_status to 'pending'."""
    print("\n" + "=" * 80)
    print("SETTING ALL DOCTORS TO PENDING")
    print("=" * 80)
    
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("ERROR: MONGO_URI not found in .env")
        return
    
    client = MongoClient(mongo_uri)
    db = client["dr_doctor_test"]
    doctors_collection = db["doctors"]
    
    result = doctors_collection.update_many(
        {},
        {"$set": {"scrape_status": "pending"}}
    )
    
    print(f"[OK] Updated {result.modified_count} doctors to 'pending' status")
    
    client.close()

def main():
    """Main function."""
    print("=" * 80)
    print("TESTING DOCTOR-HOSPITAL RELATIONSHIPS")
    print("=" * 80)
    print()
    
    # Step 1: Clear test database
    clear_test_db()
    
    # Step 2: Run sample scraper
    run_sample_scraper()
    
    # Step 3: Verify relationships
    relationships_established = verify_relationships()
    
    # Step 4: If relationships established, set doctors to pending
    if relationships_established:
        set_doctors_to_pending()
        print("\n[OK] TEST COMPLETED SUCCESSFULLY!")
    else:
        print("\n[ERROR] TEST FAILED - Relationships not established")
        print("   Please check the code and try again")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()

