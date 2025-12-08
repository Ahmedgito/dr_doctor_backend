"""Validate scraped data and generate statistics."""

import json
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()


def validate_database(test_db: bool = False) -> Dict:
    """Validate data in MongoDB and return statistics."""
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI missing in .env")
    
    client = MongoClient(mongo_uri)
    db_name = "dr_doctor_test" if test_db else "dr_doctor"
    db = client[db_name]
    
    stats = {
        'hospitals': {
            'total': db.hospitals.count_documents({}),
            'with_url': db.hospitals.count_documents({"url": {"$exists": True, "$ne": None}}),
            'with_doctors': db.hospitals.count_documents({"doctors": {"$exists": True, "$ne": []}}),
            'status_pending': db.hospitals.count_documents({"scrape_status": "pending"}),
            'status_enriched': db.hospitals.count_documents({"scrape_status": "enriched"}),
            'status_doctors_collected': db.hospitals.count_documents({"scrape_status": "doctors_collected"}),
            'with_location': db.hospitals.count_documents({"location": {"$exists": True, "$ne": None}}),
            'missing_fields': defaultdict(int),
        },
        'doctors': {
            'total': db.doctors.count_documents({}),
            'with_url': db.doctors.count_documents({"profile_url": {"$exists": True, "$ne": None}}),
            'status_pending': db.doctors.count_documents({"scrape_status": "pending"}),
            'status_processed': db.doctors.count_documents({"scrape_status": "processed"}),
            'with_hospitals': db.doctors.count_documents({"hospitals": {"$exists": True, "$ne": []}}),
            'with_private_practice': db.doctors.count_documents({"private_practice": {"$exists": True, "$ne": None}}),
            'with_qualifications': db.doctors.count_documents({"qualifications": {"$exists": True, "$ne": []}}),
            'with_services': db.doctors.count_documents({"services": {"$exists": True, "$ne": []}}),
            'missing_fields': defaultdict(int),
        },
        'issues': [],
    }
    
    # Check for hospitals missing critical fields
    hospitals = db.hospitals.find({})
    for hospital in hospitals:
        if not hospital.get('url'):
            stats['hospitals']['missing_fields']['url'] += 1
        if not hospital.get('name'):
            stats['hospitals']['missing_fields']['name'] += 1
        if not hospital.get('scrape_status'):
            stats['hospitals']['missing_fields']['scrape_status'] += 1
    
    # Check for doctors missing critical fields
    doctors = db.doctors.find({})
    for doctor in doctors:
        if not doctor.get('profile_url'):
            stats['doctors']['missing_fields']['profile_url'] += 1
        if not doctor.get('name'):
            stats['doctors']['missing_fields']['name'] += 1
        if not doctor.get('specialty') or not doctor.get('specialty'):
            stats['doctors']['missing_fields']['specialty'] += 1
    
    # Check for data quality issues
    if stats['hospitals']['total'] < stats['hospitals']['status_doctors_collected']:
        stats['issues'].append("More hospitals marked as 'doctors_collected' than total hospitals")
    
    if stats['doctors']['total'] < stats['doctors']['status_processed']:
        stats['issues'].append("More doctors marked as 'processed' than total doctors")
    
    client.close()
    return stats


def validate_export_file(file_path: Path) -> Dict:
    """Validate exported JSON file and return statistics."""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and 'items' in data:
        items = data['items']
    else:
        items = [data]
    
    stats = {
        'total': len(items),
        'with_url': 0,
        'missing_fields': defaultdict(int),
    }
    
    for item in items:
        if item.get('url') or item.get('profile_url'):
            stats['with_url'] += 1
        if not item.get('name'):
            stats['missing_fields']['name'] += 1
    
    return stats


def print_validation_report(stats: Dict, db_name: str = "dr_doctor"):
    """Print formatted validation report."""
    print("\n" + "="*80)
    print(f"DATA VALIDATION REPORT - {db_name.upper()}")
    print("="*80)
    
    print(f"\n{'='*80}")
    print("HOSPITALS")
    print(f"{'='*80}")
    print(f"Total Hospitals: {stats['hospitals']['total']}")
    print(f"  With URL: {stats['hospitals']['with_url']}")
    print(f"  With Doctors: {stats['hospitals']['with_doctors']}")
    print(f"  With Location: {stats['hospitals']['with_location']}")
    print(f"\nStatus Breakdown:")
    print(f"  Pending: {stats['hospitals']['status_pending']}")
    print(f"  Enriched: {stats['hospitals']['status_enriched']}")
    print(f"  Doctors Collected: {stats['hospitals']['status_doctors_collected']}")
    
    if stats['hospitals']['missing_fields']:
        print(f"\nMissing Fields:")
        for field, count in stats['hospitals']['missing_fields'].items():
            print(f"  {field}: {count}")
    
    print(f"\n{'='*80}")
    print("DOCTORS")
    print(f"{'='*80}")
    print(f"Total Doctors: {stats['doctors']['total']}")
    print(f"  With URL: {stats['doctors']['with_url']}")
    print(f"  With Hospitals: {stats['doctors']['with_hospitals']}")
    print(f"  With Private Practice: {stats['doctors']['with_private_practice']}")
    print(f"  With Qualifications: {stats['doctors']['with_qualifications']}")
    print(f"  With Services: {stats['doctors']['with_services']}")
    print(f"\nStatus Breakdown:")
    print(f"  Pending: {stats['doctors']['status_pending']}")
    print(f"  Processed: {stats['doctors']['status_processed']}")
    
    if stats['doctors']['missing_fields']:
        print(f"\nMissing Fields:")
        for field, count in stats['doctors']['missing_fields'].items():
            print(f"  {field}: {count}")
    
    if stats['issues']:
        print(f"\n{'='*80}")
        print("ISSUES FOUND")
        print(f"{'='*80}")
        for issue in stats['issues']:
            print(f"  ⚠ {issue}")
    else:
        print(f"\n{'='*80}")
        print("✓ No issues found")
        print(f"{'='*80}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate scraped data")
    parser.add_argument("--test-db", action="store_true", help="Validate test database")
    parser.add_argument("--export-file", type=str, help="Validate exported JSON file")
    args = parser.parse_args()
    
    if args.export_file:
        file_path = Path(args.export_file)
        if not file_path.exists():
            print(f"Error: File not found: {file_path}")
            return
        stats = validate_export_file(file_path)
        print(f"\nExport File Validation: {file_path.name}")
        print(f"Total Items: {stats['total']}")
        print(f"With URL: {stats['with_url']}")
        if stats['missing_fields']:
            print("Missing Fields:")
            for field, count in stats['missing_fields'].items():
                print(f"  {field}: {count}")
    else:
        db_name = "dr_doctor_test" if args.test_db else "dr_doctor"
        stats = validate_database(test_db=args.test_db)
        print_validation_report(stats, db_name)


if __name__ == "__main__":
    main()

