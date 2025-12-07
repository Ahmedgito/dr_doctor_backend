# Workflow Changes and Fixes

## Summary of Changes

### 1. ✅ Removed Legacy Hospital Field
- Removed `hospital: Optional[str]` field from `DoctorModel`
- Added `private_practice: Optional[dict]` field for video consultations and private practices

### 2. ✅ New Two-Phase Workflow

#### Phase 1: Hospital Collection
- Read hospitals from listing pages
- Visit each hospital URL
- Collect comprehensive hospital data (about, departments, procedures, etc.)
- Extract all doctor names and URLs from hospital pages
- Store doctor list in `hospital.doctors` (minimal: name + profile_url)
- **Do NOT process doctors yet** - just collect their URLs

#### Phase 2: Doctor Processing
- Process all collected doctor URLs
- Enrich each doctor profile (qualifications, experience, services, etc.)
- Separate hospitals from private practices (video consultations)
- Update `hospital.doctors` with full doctor info (fee, timings) when hospital URLs found
- Update `doctor.hospitals` with hospital affiliations

### 3. ✅ Hospital URL Parsing
- Created `url_parser.py` utility
- Extracts city, name, area from URL: `marham.pk/hospitals/(city)/(name)/(area)`
- Example: `marham.pk/hospitals/karachi/hashmanis-hospital-m-a-jinnah-road/jacob-lines`
  - city: "Karachi"
  - name: "Hashmanis Hospital M A Jinnah Road"
  - area: "Jacob Lines"

### 4. ✅ Video Consultation Handling
- Video consultations are now stored as `doctor.private_practice`
- Not treated as hospitals
- Format: `{name: str, url: str, fee: int, timings: dict}`

### 5. ✅ Hospital-Doctor Relationship Fixes
- Hospitals are now properly updated with doctor information
- Doctor entries in `hospital.doctors` include: name, profile_url, fee, timings
- Updates happen in Phase 2 when processing doctors

### 6. ✅ Database Export Script
- Created `scripts/export_and_clear_db.py`
- Exports all data to JSON for review
- Optionally clears database after export

## New Data Flow

```
1. Scrape hospital listing pages
   ↓
2. For each hospital:
   - Load hospital page
   - Parse hospital data (about, departments, etc.)
   - Extract doctor names + URLs
   - Save hospital with doctor list (minimal)
   ↓
3. Collect all unique doctor URLs
   ↓
4. For each doctor:
   - Load doctor profile page
   - Parse doctor data (qualifications, services, etc.)
   - Process practices:
     * Real hospitals → add to doctor.hospitals, update hospital.doctors
     * Private practice → add to doctor.private_practice
   - Save/update doctor
```

## Key Improvements

1. **Better Data Quality**: Hospitals are fully enriched before processing doctors
2. **Proper Relationships**: Hospital-doctor relationships are correctly maintained
3. **Private Practice Support**: Video consultations handled separately
4. **URL-Based Lookups**: More reliable hospital identification using URLs
5. **Deduplication**: Doctors processed once even if found at multiple hospitals

## Usage

### Export and Review Database
```powershell
cd dr_doctor_scraper
python scripts/export_and_clear_db.py --clear
```

This will:
1. Export all doctors to `data/exports/doctors_backup_TIMESTAMP.json`
2. Export all hospitals to `data/exports/hospitals_backup_TIMESTAMP.json`
3. Clear the database (if --clear flag used)

### Run Scraper (Entry Point Unchanged)
```powershell
python run_scraper.py --site marham --limit 5
```

## Files Modified

1. `scrapers/models/doctor_model.py` - Removed legacy hospital field, added private_practice
2. `scrapers/marham_scraper.py` - New two-phase workflow
3. `scrapers/marham/parsers/hospital_parser.py` - URL parsing for city/name/area
4. `scrapers/marham/enrichers/profile_enricher.py` - Private practice detection
5. `scrapers/marham/handlers/hospital_practice_handler.py` - URL-based hospital lookup
6. `scrapers/utils/url_parser.py` - New utility for URL parsing
7. `scripts/export_and_clear_db.py` - New export script

## Testing Recommendations

1. Export current DB and review for issues
2. Clear database
3. Run scraper with `--limit 5` to test new workflow
4. Verify:
   - Hospitals have complete data
   - Hospitals have doctor lists
   - Doctors have hospital affiliations
   - Video consultations are in private_practice, not hospitals
   - Hospital URLs correctly parsed for city/name/area

