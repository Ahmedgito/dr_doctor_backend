# Testing Environment Guide

This guide explains how to use the testing environment to safely test scraper changes without affecting production data.

## Overview

The testing environment provides:
- **Separate Database**: `dr_doctor_test` (vs production `dr_doctor`)
- **Performance Testing**: Compare scraping speeds with/without JavaScript
- **Data Validation**: Validate scraped data quality
- **Log Analysis**: Analyze performance metrics from test runs

## Quick Start

### 1. Run Tests with Test Database

```powershell
# Test with limit (uses test DB)
python run_scraper.py --site marham --limit 100 --test-db

# Test with multi-threading (much faster)
python run_scraper.py --site marham --limit 100 --test-db --threads 4

# Test without JavaScript (faster, but buttons may not work)
python run_scraper.py --site marham --limit 100 --test-db --disable-js
```

### 2. Validate Test Data

```powershell
# Validate test database
python scripts/validate_data.py --test-db

# Validate production database
python scripts/validate_data.py
```

### 3. Analyze Logs

```powershell
# Analyze all runs
python scripts/analyze_logs.py

# Analyze specific limit runs
python scripts/analyze_logs.py --limit 1000
```

## Features

### Test Database (`--test-db`)

When using `--test-db`, the scraper uses `dr_doctor_test` database instead of `dr_doctor`. This ensures:
- Production data is never modified
- You can safely test scraper changes
- You can compare test runs

**Example:**
```powershell
# Production run
python run_scraper.py --site marham --limit 1000

# Test run (separate DB)
python run_scraper.py --site marham --limit 1000 --test-db
```

### Multi-Threading (`--threads`)

**Recommended for faster scraping!** Use multiple threads to process pages/hospitals/doctors in parallel:
- 4-8x faster than single-threaded
- Each thread has its own browser instance
- Work is distributed evenly across threads

**Example:**
```powershell
# Single-threaded (default)
python run_scraper.py --site marham --limit 100 --test-db

# Multi-threaded with 4 threads (4x faster)
python run_scraper.py --site marham --limit 100 --test-db --threads 4

# Multi-threaded with 8 threads (6-8x faster)
python run_scraper.py --site marham --limit 1000 --test-db --threads 8
```

**Note**: See `MULTITHREADING.md` for detailed guide on multi-threading.

### Disable JavaScript (`--disable-js`)

**Note**: This doesn't work well with Marham because "Load More" buttons require JavaScript. Use `--threads` instead for faster scraping.

If the website works without JavaScript, disabling it can speed up scraping:
- Faster page loads (no JS execution)
- Lower resource usage
- Use `wait_until="domcontentloaded"` instead of `"networkidle"`

**Example:**
```powershell
# Normal scraping (with JS)
python run_scraper.py --site marham --limit 100 --test-db

# Fast scraping (no JS) - may not work for sites with JS-dependent buttons
python run_scraper.py --site marham --limit 100 --test-db --disable-js
```

**Note**: Test first to ensure the site works without JavaScript. Some sites require JS for:
- Dynamic content loading
- "Load More" buttons (like Marham)
- Form submissions

## Data Validation

The validation script checks:
- Total counts (hospitals, doctors)
- Status breakdown (pending, enriched, processed)
- Missing critical fields
- Data quality issues

**Example Output:**
```
================================================================================
DATA VALIDATION REPORT - DR_DOCTOR_TEST
================================================================================

================================================================================
HOSPITALS
================================================================================
Total Hospitals: 1000
  With URL: 1000
  With Doctors: 850
  With Location: 750

Status Breakdown:
  Pending: 0
  Enriched: 0
  Doctors Collected: 1000

================================================================================
DOCTORS
================================================================================
Total Doctors: 5000
  With URL: 5000
  With Hospitals: 4500
  With Qualifications: 4800
  With Services: 4700

Status Breakdown:
  Pending: 0
  Processed: 5000
```

## Log Analysis

The log analysis script extracts:
- Total runs and runs by limit
- Aggregate statistics (hospitals, doctors, pages)
- Performance metrics (average times per step)
- Detailed run information

**Example Output:**
```
================================================================================
SCRAPER LOG ANALYSIS REPORT
================================================================================

Total Runs Analyzed: 2

Runs by Limit:
  Limit 1000: 2 run(s)

================================================================================
AGGREGATE STATISTICS
================================================================================
Total Hospitals Collected: 2000
Total Hospitals Enriched: 2000
Total Doctors Collected: 10000
Total Doctors Processed: 10000
Total Pages Scraped: 200
Total Errors: 0

================================================================================
PERFORMANCE METRICS
================================================================================
Average Step 1 Time (Collection): 120.50 seconds
Average Step 2 Time (Enrichment): 1800.25 seconds
Average Step 3 Time (Processing): 3600.00 seconds
Average Total Time: 5520.75 seconds (92.01 minutes)
Average Hospitals per Page: 10.00
Average Time per Hospital: 0.90 seconds
Average Time per Doctor: 0.36 seconds
```

## Comparing Test Runs

### Step 1: Run Baseline Test
```powershell
python run_scraper.py --site marham --limit 100 --test-db
```

### Step 2: Run Optimized Test
```powershell
python run_scraper.py --site marham --limit 100 --test-db --disable-js
```

### Step 3: Compare Results
```powershell
# Analyze logs
python scripts/analyze_logs.py --limit 100

# Validate both databases
python scripts/validate_data.py --test-db
```

## Troubleshooting

### Issue: Only 600-700 hospitals collected with limit=1000

**Possible Causes:**
1. **Pagination ends early**: The listing pages may not have 1000 hospitals
2. **Duplicate filtering**: Some hospitals may be skipped as duplicates
3. **Scraping stopped**: Check logs for errors or early termination

**Solution:**
```powershell
# Check actual count in database
python scripts/validate_data.py --test-db

# Review logs for pagination issues
python scripts/analyze_logs.py --limit 1000
```

### Issue: Scraping is too slow

**Solutions:**
1. **Use multi-threading** (recommended):
   ```powershell
   python run_scraper.py --site marham --limit 100 --test-db --threads 4
   ```
   This can be 4-8x faster!

2. **Disable JavaScript** (if site supports it, but not recommended for Marham):
   ```powershell
   python run_scraper.py --site marham --limit 100 --test-db --disable-js
   ```

3. **Reduce wait times**: Edit `base_scraper.py` timeout settings

4. **Use headless mode**: Already default, but ensure `--headless` is set

### Issue: Data validation shows missing fields

**Check:**
- Are hospitals/doctors in "pending" status? (not yet enriched)
- Are there parsing errors in logs?
- Is the website structure changed?

**Solution:**
```powershell
# Check status breakdown
python scripts/validate_data.py --test-db

# Review logs for parsing errors
Get-Content logs\dr_doctor_scraper.log | Select-String -Pattern "ERROR|WARNING"
```

## Best Practices

1. **Always use `--test-db` for testing**: Protects production data
2. **Test with small limits first**: Use `--limit 10` before `--limit 1000`
3. **Validate after each run**: Check data quality with validation script
4. **Compare performance**: Run with/without `--disable-js` to find optimal settings
5. **Review logs**: Use log analysis to understand performance bottlenecks

## Example Test Workflow

```powershell
# 1. Small test run with multi-threading
python run_scraper.py --site marham --limit 10 --test-db --threads 4

# 2. Validate results
python scripts/validate_data.py --test-db

# 3. Analyze performance
python scripts/analyze_logs.py --limit 10

# 4. If good, run larger test with more threads
python run_scraper.py --site marham --limit 100 --test-db --threads 4

# 5. Compare with production data
python scripts/validate_data.py  # Production
python scripts/validate_data.py --test-db  # Test

# 6. Full test run with optimal thread count
python run_scraper.py --site marham --limit 1000 --test-db --threads 6
```

