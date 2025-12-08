# Running Scraper Steps Independently

## Overview

The scraper now supports running individual steps independently. This is useful when:
- Step 1 didn't complete all pages
- You want to process pending hospitals/doctors
- You need to resume from a specific step

## Step Breakdown

### Step 1: Collect Hospitals from Listing Pages
- Scrapes hospital listing pages
- Extracts basic hospital information (name, URL, address, location)
- Saves hospitals to database with `scrape_status="pending"`

### Step 2: Enrich Hospitals and Collect Doctors
- Processes hospitals with `scrape_status="pending"` or `"enriched"`
- Enriches hospital data (About section, departments, etc.)
- Collects doctor URLs from hospital pages
- Saves minimal doctor records with `scrape_status="pending"`
- Updates hospital status to `"doctors_collected"`

### Step 3: Process Doctor Profiles
- Processes doctors with `scrape_status="pending"`
- Enriches doctor profiles (qualifications, services, etc.)
- Updates doctor status to `"processed"`

## Usage

### Run All Steps (Default)
```powershell
python run_scraper.py --site marham --threads 4
```

### Run Only Step 1 (Collect Hospitals)
```powershell
python run_scraper.py --site marham --threads 4 --step 1
```

### Run Only Step 2 (Enrich Hospitals)
```powershell
python run_scraper.py --site marham --threads 4 --step 2
```

### Run Only Step 3 (Process Doctors)
```powershell
python run_scraper.py --site marham --threads 4 --step 3
```

## Common Workflows

### 1. Complete Initial Collection
```powershell
# Step 1: Collect all hospitals
python run_scraper.py --site marham --threads 4 --step 1

# Step 2: Enrich hospitals and collect doctors
python run_scraper.py --site marham --threads 4 --step 2

# Step 3: Process all doctors
python run_scraper.py --site marham --threads 4 --step 3
```

### 2. Process Pending Items
```powershell
# Check how many hospitals are pending
python scripts/validate_data.py

# Process pending hospitals
python run_scraper.py --site marham --threads 4 --step 2

# Process pending doctors
python run_scraper.py --site marham --threads 4 --step 3
```

### 3. Resume After Interruption
```powershell
# If Step 1 was interrupted, continue collecting
python run_scraper.py --site marham --threads 4 --step 1

# Then continue with Step 2 and 3
python run_scraper.py --site marham --threads 4 --step 2
python run_scraper.py --site marham --threads 4 --step 3
```

## Step 1 Improvements

### Automatic Page Tracking
- Step 1 now processes pages in batches
- Stops automatically after 5 consecutive empty pages
- Can be resumed by running Step 1 again (will continue from where it left off)

### Better Progress Tracking
- Logs show which pages are being processed
- Tracks consecutive empty pages
- Stops when no more hospitals are found

## Step 2 & 3 Improvements

### Independent Execution
- Can run Step 2 and Step 3 independently
- Processes all pending items (not limited by `--limit`)
- Shows count of items to process before starting

### Resumable
- If interrupted, just run the step again
- Will process all remaining pending items
- No need to start from the beginning

## Examples

### Example 1: Process Only Pending Doctors
```powershell
# Check status
python scripts/validate_data.py

# Process pending doctors
python run_scraper.py --site marham --threads 6 --step 3
```

### Example 2: Complete Hospital Collection
```powershell
# Collect all hospitals (no limit)
python run_scraper.py --site marham --threads 4 --step 1

# Verify collection
python scripts/validate_data.py

# Enrich all hospitals
python run_scraper.py --site marham --threads 4 --step 2
```

### Example 3: Test with Small Limit
```powershell
# Collect 10 hospitals
python run_scraper.py --site marham --threads 2 --limit 10 --step 1

# Enrich those 10 hospitals
python run_scraper.py --site marham --threads 2 --step 2

# Process doctors from those hospitals
python run_scraper.py --site marham --threads 2 --step 3
```

## Notes

- **`--limit` flag**: Only affects Step 1 (hospital collection). Step 2 and Step 3 process ALL pending items regardless of limit.
- **Resumable**: All steps are resumable - if interrupted, just run the step again.
- **Status tracking**: Use `scrape_status` field to track progress:
  - Hospitals: `"pending"` → `"enriched"` → `"doctors_collected"`
  - Doctors: `"pending"` → `"processed"`

## Troubleshooting

### Issue: Step 1 stops too early
**Solution**: Run Step 1 again - it will continue from where it left off.

### Issue: Many hospitals in "pending" status
**Solution**: Run Step 2 to process them:
```powershell
python run_scraper.py --site marham --threads 4 --step 2
```

### Issue: Many doctors in "pending" status
**Solution**: Run Step 3 to process them:
```powershell
python run_scraper.py --site marham --threads 4 --step 3
```

### Issue: Want to check what's pending
**Solution**: Use validation script:
```powershell
python scripts/validate_data.py
```

