"""Script to verify bidirectional relationships between doctors and hospitals in the database."""

import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def verify_relationships():
    """Verify that doctors have hospitals and hospitals have doctors."""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        print("ERROR: MONGO_URI not found in .env")
        return
    
    client = MongoClient(mongo_uri)
    db = client["dr_doctor"]
    
    doctors_collection = db["doctors"]
    hospitals_collection = db["hospitals"]
    
    print("=" * 80)
    print("DATABASE RELATIONSHIP VERIFICATION")
    print("=" * 80)
    print()
    
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
    doctors_without_hospitals = total_doctors - doctors_with_hospitals
    
    print("=" * 80)
    print("DOCTORS -> HOSPITALS RELATIONSHIP")
    print("=" * 80)
    print(f"Doctors WITH hospitals list: {doctors_with_hospitals} ({doctors_with_hospitals/total_doctors*100:.1f}%)" if total_doctors > 0 else "Doctors WITH hospitals list: 0")
    print(f"Doctors WITHOUT hospitals list: {doctors_without_hospitals} ({doctors_without_hospitals/total_doctors*100:.1f}%)" if total_doctors > 0 else "Doctors WITHOUT hospitals list: 0")
    print()
    
    # Sample doctors with hospitals
    if doctors_with_hospitals > 0:
        print("Sample doctors WITH hospitals:")
        sample_doctors = list(doctors_collection.find(
            {"hospitals": {"$exists": True, "$ne": None, "$ne": []}},
            {"name": 1, "profile_url": 1, "hospitals": 1}
        ).limit(5))
        for doc in sample_doctors:
            hospitals_count = len(doc.get("hospitals", []))
            print(f"  - {doc.get('name', 'Unknown')}: {hospitals_count} hospital(s)")
            if hospitals_count > 0:
                first_hosp = doc.get("hospitals", [])[0]
                if isinstance(first_hosp, dict):
                    print(f"    First hospital: {first_hosp.get('name', 'Unknown')} ({first_hosp.get('url', 'No URL')})")
        print()
    
    # Sample doctors without hospitals
    if doctors_without_hospitals > 0:
        print("Sample doctors WITHOUT hospitals:")
        sample_doctors = list(doctors_collection.find(
            {"$or": [
                {"hospitals": {"$exists": False}},
                {"hospitals": None},
                {"hospitals": []}
            ]},
            {"name": 1, "profile_url": 1, "scrape_status": 1}
        ).limit(5))
        for doc in sample_doctors:
            status = doc.get("scrape_status", "unknown")
            print(f"  - {doc.get('name', 'Unknown')}: status={status}")
        print()
    
    # Check hospitals with doctors
    hospitals_with_doctors = hospitals_collection.count_documents({
        "doctors": {"$exists": True, "$ne": None, "$ne": []}
    })
    hospitals_without_doctors = total_hospitals - hospitals_with_doctors
    
    print("=" * 80)
    print("HOSPITALS -> DOCTORS RELATIONSHIP")
    print("=" * 80)
    print(f"Hospitals WITH doctors list: {hospitals_with_doctors} ({hospitals_with_doctors/total_hospitals*100:.1f}%)" if total_hospitals > 0 else "Hospitals WITH doctors list: 0")
    print(f"Hospitals WITHOUT doctors list: {hospitals_without_doctors} ({hospitals_without_doctors/total_hospitals*100:.1f}%)" if total_hospitals > 0 else "Hospitals WITHOUT doctors list: 0")
    print()
    
    # Sample hospitals with doctors
    if hospitals_with_doctors > 0:
        print("Sample hospitals WITH doctors:")
        sample_hospitals = list(hospitals_collection.find(
            {"doctors": {"$exists": True, "$ne": None, "$ne": []}},
            {"name": 1, "url": 1, "doctors": 1}
        ).limit(5))
        for hosp in sample_hospitals:
            doctors_count = len(hosp.get("doctors", []))
            print(f"  - {hosp.get('name', 'Unknown')}: {doctors_count} doctor(s)")
            if doctors_count > 0:
                first_doc = hosp.get("doctors", [])[0]
                if isinstance(first_doc, dict):
                    print(f"    First doctor: {first_doc.get('name', 'Unknown')} ({first_doc.get('profile_url', 'No URL')})")
        print()
    
    # Sample hospitals without doctors
    if hospitals_without_doctors > 0:
        print("Sample hospitals WITHOUT doctors:")
        sample_hospitals = list(hospitals_collection.find(
            {"$or": [
                {"doctors": {"$exists": False}},
                {"doctors": None},
                {"doctors": []}
            ]},
            {"name": 1, "url": 1, "scrape_status": 1}
        ).limit(5))
        for hosp in sample_hospitals:
            status = hosp.get("scrape_status", "unknown")
            print(f"  - {hosp.get('name', 'Unknown')}: status={status}")
        print()
    
    # Cross-verification: Check if relationships are bidirectional
    print("=" * 80)
    print("BIDIRECTIONAL RELATIONSHIP VERIFICATION")
    print("=" * 80)
    
    # Find doctors with hospitals and verify reverse relationship
    doctors_with_hospitals_list = list(doctors_collection.find(
        {"hospitals": {"$exists": True, "$ne": None, "$ne": []}},
        {"name": 1, "profile_url": 1, "hospitals": 1}
    ).limit(100))
    
    verified_bidirectional = 0
    missing_reverse = 0
    
    for doctor in doctors_with_hospitals_list:
        doctor_url = doctor.get("profile_url")
        hospitals = doctor.get("hospitals", [])
        
        for hosp_entry in hospitals:
            if isinstance(hosp_entry, dict):
                hosp_url = hosp_entry.get("url")
                if hosp_url:
                    # Check if hospital has this doctor in its doctors list
                    hospital = hospitals_collection.find_one({"url": hosp_url})
                    if hospital:
                        doctors_list = hospital.get("doctors", [])
                        # Check if doctor is in hospital's doctors list
                        found = False
                        for doc_entry in doctors_list:
                            if isinstance(doc_entry, dict) and doc_entry.get("profile_url") == doctor_url:
                                found = True
                                break
                        
                        if found:
                            verified_bidirectional += 1
                        else:
                            missing_reverse += 1
                            if missing_reverse <= 5:  # Show first 5 examples
                                print(f"  WARNING: Doctor {doctor.get('name')} has hospital {hosp_entry.get('name')}, but hospital doesn't have doctor")
    
    print(f"Verified bidirectional relationships: {verified_bidirectional}")
    print(f"Missing reverse relationships: {missing_reverse}")
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"[OK] Doctors with hospitals: {doctors_with_hospitals}/{total_doctors}")
    print(f"[OK] Hospitals with doctors: {hospitals_with_doctors}/{total_hospitals}")
    print(f"[OK] Verified bidirectional: {verified_bidirectional}")
    print(f"[WARN] Missing reverse relationships: {missing_reverse}")
    print()
    
    if missing_reverse > 0:
        print("WARNING: Some relationships are not bidirectional!")
        print("   This means some doctors reference hospitals that don't reference them back.")
    else:
        print("[OK] All relationships appear to be bidirectional!")
    
    client.close()

if __name__ == "__main__":
    verify_relationships()

