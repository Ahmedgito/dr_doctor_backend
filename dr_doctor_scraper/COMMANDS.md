# Command Reference Guide

Complete reference for all commands and scripts in the Dr.Doctor Scraper project.

## Table of Contents

1. [Main Scraper Commands](#main-scraper-commands)
2. [Analysis & Validation Commands](#analysis--validation-commands)
3. [Database Management Commands](#database-management-commands)
4. [Common Workflows](#common-workflows)

---

## Main Scraper Commands

### Basic Scraping

```powershell
# Single-threaded scraping (default)
python run_scraper.py --site marham

# Multi-threaded scraping (4 threads)
python run_scraper.py --site marham --threads 4

# Scrape with limit (for testing)
python run_scraper.py --site marham --limit 100

# Scrape with visible browser (debugging)
python run_scraper.py --site marham --no-headless
```

### Step-by-Step Execution

```powershell
# Step 1: Collect hospitals from listing pages
python run_scraper.py --site marham --threads 4 --step 1

# Step 2: Enrich hospitals and collect doctors
python run_scraper.py --site marham --threads 4 --step 2

# Step 3: Process doctor profiles
python run_scraper.py --site marham --threads 4 --step 3
```

### Test Database

```powershell
# Use test database (safe for testing)
python run_scraper.py --site marham --threads 4 --test-db

# Test with limit
python run_scraper.py --site marham --limit 10 --test-db --threads 2
```

### Complete Examples

```powershell
# Full production run (all steps, multi-threaded)
python run_scraper.py --site marham --threads 6

# Test run with small limit
python run_scraper.py --site marham --limit 10 --threads 2 --test-db

# Process only pending hospitals
python run_scraper.py --site marham --threads 4 --step 2

# Process only pending doctors
python run_scraper.py --site marham --threads 4 --step 3
```

---

## Analysis & Validation Commands

### Log Analysis

```powershell
# Analyze all runs in log file
python scripts/analyze_logs.py

# Analyze specific limit runs
python scripts/analyze_logs.py --limit 1000

# Analyze custom log file
python scripts/analyze_logs.py --log-file logs/custom.log
```

### Log Diagnostics

```powershell
# Detailed diagnostics for last run
python scripts/log_diagnostics.py

# Diagnostics for custom log file
python scripts/log_diagnostics.py --log-file logs/custom.log
```

### Data Validation

```powershell
# Validate production database
python scripts/validate_data.py

# Validate test database
python scripts/validate_data.py --test-db

# Validate exported JSON file
python scripts/validate_data.py --export-file data/exports/hospitals_backup.json
```

---

## Database Management Commands

### Export Database

```powershell
# Export database to JSON (keeps data in DB)
python scripts/export_and_clear_db.py

# Export and clear database
python scripts/export_and_clear_db.py --clear
```

### Import/Export Tools

```powershell
# Export hospitals to JSON
python scrapers/tools/export_db.py --collection hospitals --out hospitals.json --format json --pretty

# Export doctors to CSV
python scrapers/tools/export_db.py --collection doctors --out doctors.csv --format csv

# Import from JSON
python scrapers/tools/import_db.py --collection hospitals --in hospitals.json --format json
```

---

## Common Workflows

### Workflow 1: Initial Data Collection

```powershell
# 1. Collect all hospitals
python run_scraper.py --site marham --threads 4 --step 1

# 2. Validate collection
python scripts/validate_data.py

# 3. Enrich hospitals and collect doctors
python run_scraper.py --site marham --threads 4 --step 2

# 4. Process all doctors
python run_scraper.py --site marham --threads 4 --step 3

# 5. Final validation
python scripts/validate_data.py
```

### Workflow 2: Process Pending Items

```powershell
# 1. Check what's pending
python scripts/validate_data.py

# 2. Process pending hospitals
python run_scraper.py --site marham --threads 4 --step 2

# 3. Process pending doctors
python run_scraper.py --site marham --threads 4 --step 3

# 4. Verify completion
python scripts/validate_data.py
```

### Workflow 3: Testing New Changes

```powershell
# 1. Small test run
python run_scraper.py --site marham --limit 10 --threads 2 --test-db

# 2. Validate test results
python scripts/validate_data.py --test-db

# 3. Analyze performance
python scripts/analyze_logs.py --limit 10

# 4. If good, run larger test
python run_scraper.py --site marham --limit 100 --threads 4 --test-db
```

### Workflow 4: Resume After Interruption

```powershell
# 1. Check current status
python scripts/validate_data.py

# 2. Continue from where it stopped
# If Step 1 was interrupted:
python run_scraper.py --site marham --threads 4 --step 1

# If Step 2 was interrupted:
python run_scraper.py --site marham --threads 4 --step 2

# If Step 3 was interrupted:
python run_scraper.py --site marham --threads 4 --step 3
```

### Workflow 5: Performance Analysis

```powershell
# 1. Run scraper with logging
python run_scraper.py --site marham --threads 4 --limit 100

# 2. Analyze logs
python scripts/analyze_logs.py --limit 100

# 3. Get detailed diagnostics
python scripts/log_diagnostics.py

# 4. Compare with previous runs
python scripts/analyze_logs.py
```

### Workflow 6: Database Backup & Restore

```powershell
# 1. Export current database
python scripts/export_and_clear_db.py

# 2. (Optional) Clear database
python scripts/export_and_clear_db.py --clear

# 3. Import from backup
python scrapers/tools/import_db.py --collection hospitals --in data/exports/hospitals_backup_YYYYMMDD_HHMMSS.json --format json
python scrapers/tools/import_db.py --collection doctors --in data/exports/doctors_backup_YYYYMMDD_HHMMSS.json --format json
```

---

## Command Options Reference

### `run_scraper.py` Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--site` | str | required | Site to scrape: 'marham', 'oladoc', or 'all' |
| `--headless` | flag | True | Run browser in headless mode |
| `--no-headless` | flag | False | Run browser with visible UI |
| `--limit` | int | None | Limit number of profiles per site |
| `--disable-js` | flag | False | Disable JavaScript (faster, but may break some sites) |
| `--test-db` | flag | False | Use test database (dr_doctor_test) |
| `--threads` | int | 1 | Number of worker threads (1-8 recommended) |
| `--step` | int | None | Run only specific step (1, 2, or 3) |

### `analyze_logs.py` Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--log-file` | str | logs/dr_doctor_scraper.log | Path to log file |
| `--limit` | int | None | Filter runs by limit value |

### `validate_data.py` Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--test-db` | flag | False | Validate test database |
| `--export-file` | str | None | Validate exported JSON file |

### `export_and_clear_db.py` Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--clear` | flag | False | Clear database after export |

### `log_diagnostics.py` Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--log-file` | str | logs/dr_doctor_scraper.log | Path to log file |

---

## Tips & Best Practices

1. **Always test with `--test-db` first** before running on production data
2. **Use `--limit` for testing** to avoid long runs during development
3. **Start with fewer threads** (2-4) and increase if stable
4. **Run validation after each step** to catch issues early
5. **Export database regularly** as backups
6. **Use `--step` to resume** if a run is interrupted
7. **Check logs** if something seems wrong: `python scripts/log_diagnostics.py`

---

## Troubleshooting Commands

```powershell
# Check for errors in logs
Get-Content logs\dr_doctor_scraper.log | Select-String -Pattern "ERROR"

# Check recent activity
Get-Content logs\dr_doctor_scraper.log -Tail 100

# Count processed items
python scripts/validate_data.py

# Analyze performance issues
python scripts/log_diagnostics.py
```

