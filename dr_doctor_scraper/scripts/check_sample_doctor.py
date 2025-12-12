"""Check a sample doctor record to see what fields are stored."""

import os
import sys
import json
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def check_sample_doctor():
    """Check a sample doctor record."""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("ERROR: MONGO_URI not found in .env")
        return
    
    client = MongoClient(mongo_uri)
    db = client["dr_doctor"]
    doctors_collection = db["doctors"]
    
    # Get a sample processed doctor
    sample_doctor = doctors_collection.find_one({"scrape_status": "processed"})
    
    if not sample_doctor:
        print("No processed doctors found")
        return
    
    print("=" * 80)
    print("SAMPLE DOCTOR RECORD")
    print("=" * 80)
    print(f"Name: {sample_doctor.get('name')}")
    print(f"Profile URL: {sample_doctor.get('profile_url')}")
    print(f"Status: {sample_doctor.get('scrape_status')}")
    print()
    
    # Check for hospitals field
    hospitals = sample_doctor.get("hospitals")
    print(f"Hospitals field exists: {hospitals is not None}")
    print(f"Hospitals field type: {type(hospitals)}")
    print(f"Hospitals field value: {hospitals}")
    print()
    
    # Show all fields
    print("All fields in doctor record:")
    for key, value in sample_doctor.items():
        if key == "_id":
            continue
        if isinstance(value, (list, dict)) and value:
            print(f"  {key}: {type(value).__name__} with {len(value) if isinstance(value, list) else 'items'}")
        elif isinstance(value, str) and len(value) > 100:
            print(f"  {key}: {value[:100]}...")
        else:
            print(f"  {key}: {value}")
    
    # Check if hospitals is None, empty list, or missing
    if hospitals is None:
        print("\n[ISSUE] Hospitals field is None")
    elif hospitals == []:
        print("\n[ISSUE] Hospitals field is empty list")
    elif not hospitals:
        print("\n[ISSUE] Hospitals field is falsy")
    else:
        print(f"\n[OK] Hospitals field has {len(hospitals)} entries")
        print("First hospital:", json.dumps(hospitals[0] if hospitals else None, indent=2))
    
    client.close()

if __name__ == "__main__":
    check_sample_doctor()

