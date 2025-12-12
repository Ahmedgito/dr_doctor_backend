# Test Commands - Quick Reference

## Clear Test Database and Run Sample Test

### Option 1: Manual Step-by-Step

```powershell
# 1. Clear test database
cd dr_doctor_scraper
python scripts\clear_db.py --test-db
# Type 'yes' when prompted

# 2. Run Step 0: Collect cities
python run_scraper.py --site marham --step 0 --test-db

# 3. Run Step 1: Collect 5 hospitals
python run_scraper.py --site marham --step 1 --limit 5 --threads 2 --test-db

# 4. Run Step 2: Enrich hospitals and collect doctors
python run_scraper.py --site marham --step 2 --threads 2 --test-db

# 5. Run Step 3: Process doctor profiles
python run_scraper.py --site marham --step 3 --threads 2 --test-db

# 6. Verify relationships
python scripts\verify_db_relationships.py

# 7. Validate data
python scripts\validate_data.py --test-db
```

### Option 2: Automated Test Script

```powershell
# Run the automated test script (clears DB, runs all steps, verifies relationships)
cd dr_doctor_scraper
python scripts\test_relationships.py
```

### Option 3: Quick All-in-One (Single Command)

```powershell
# Clear test DB and run all steps with 5 hospital limit
cd dr_doctor_scraper
python scripts\clear_db.py --test-db
# Type 'yes' when prompted, then:
python run_scraper.py --site marham --limit 5 --threads 2 --test-db
python scripts\verify_db_relationships.py
python scripts\validate_data.py --test-db
```

## Individual Commands

### Clear Test Database
```powershell
cd dr_doctor_scraper
python scripts\clear_db.py --test-db
```

### Run All Steps (5 hospitals)
```powershell
cd dr_doctor_scraper
python run_scraper.py --site marham --limit 5 --threads 2 --test-db
```

### Verify Relationships
```powershell
cd dr_doctor_scraper
python scripts\verify_db_relationships.py
```

### Validate Data
```powershell
cd dr_doctor_scraper
python scripts\validate_data.py --test-db
```

### Check Sample Doctor
```powershell
cd dr_doctor_scraper
python scripts\check_sample_doctor.py
```

## Notes

- `--test-db` flag ensures you're using the test database (`dr_doctor_test`)
- `--limit 5` limits Step 1 to collect 5 hospitals
- `--threads 2` uses 2 threads for faster processing (adjust as needed)
- The automated test script (`test_relationships.py`) does everything automatically

