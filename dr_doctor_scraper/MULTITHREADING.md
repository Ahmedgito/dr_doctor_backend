# Multi-Threading Guide

## Overview

The scraper now supports multi-threaded execution to significantly speed up data collection. Instead of processing pages, hospitals, and doctors sequentially, multiple worker threads can process them in parallel.

## How It Works

### Architecture

- **Each thread has its own browser instance**: Prevents conflicts and allows true parallel processing
- **Work distribution**: Tasks are evenly distributed across threads
  - Step 1: Different listing pages are assigned to different threads
  - Step 2: Different hospitals are assigned to different threads
  - Step 3: Different doctors are assigned to different threads
- **Thread-safe operations**: MongoDB operations are thread-safe, and statistics are synchronized with locks

### Performance Benefits

- **4-8x faster**: With 4-8 threads, you can expect 4-8x speedup (depending on network and CPU)
- **Better resource utilization**: While one thread waits for a page to load, others continue processing
- **Scalable**: Can adjust thread count based on your system resources

## Usage

### Basic Usage

```powershell
# Single-threaded (default)
python run_scraper.py --site marham --limit 100

# Multi-threaded with 4 threads
python run_scraper.py --site marham --limit 100 --threads 4

# Multi-threaded with 8 threads (faster)
python run_scraper.py --site marham --limit 1000 --threads 8
```

### With Test Database

```powershell
# Test with 4 threads
python run_scraper.py --site marham --limit 100 --threads 4 --test-db
```

### Recommended Thread Counts

- **4 threads**: Good balance for most systems
- **6-8 threads**: For faster systems with good network connection
- **2-3 threads**: For slower systems or limited resources
- **1 thread**: Default, single-threaded mode

**Note**: More threads isn't always better. Too many threads can:
- Overwhelm the target website (may get rate-limited)
- Use too much system memory (each browser instance uses ~100-200MB)
- Cause network congestion

## How Tasks Are Distributed

### Step 1: Hospital Collection

If you have 100 pages and 4 threads:
- Thread 1: Pages 1-25
- Thread 2: Pages 26-50
- Thread 3: Pages 51-75
- Thread 4: Pages 76-100

Each thread processes its assigned pages independently.

### Step 2: Hospital Enrichment

If you have 1000 hospitals and 4 threads:
- Thread 1: Hospitals 1-250
- Thread 2: Hospitals 251-500
- Thread 3: Hospitals 501-750
- Thread 4: Hospitals 751-1000

Each thread enriches its assigned hospitals and collects doctors.

### Step 3: Doctor Processing

If you have 5000 doctors and 4 threads:
- Thread 1: Doctors 1-1250
- Thread 2: Doctors 1251-2500
- Thread 3: Doctors 2501-3750
- Thread 4: Doctors 3751-5000

Each thread processes its assigned doctors independently.

## Performance Comparison

### Example: Scraping 1000 Hospitals

**Single-threaded (1 thread)**:
- Step 1: ~10 minutes (collecting hospitals)
- Step 2: ~30 minutes (enriching hospitals)
- Step 3: ~60 minutes (processing doctors)
- **Total: ~100 minutes**

**Multi-threaded (4 threads)**:
- Step 1: ~3 minutes (4x faster)
- Step 2: ~8 minutes (4x faster)
- Step 3: ~15 minutes (4x faster)
- **Total: ~26 minutes** (almost 4x speedup)

**Multi-threaded (8 threads)**:
- Step 1: ~2 minutes (5x faster)
- Step 2: ~5 minutes (6x faster)
- Step 3: ~10 minutes (6x faster)
- **Total: ~17 minutes** (almost 6x speedup)

*Note: Actual times depend on network speed, system resources, and website response times.*

## Best Practices

### 1. Start Small

Test with a small limit first:
```powershell
python run_scraper.py --site marham --limit 10 --threads 4 --test-db
```

### 2. Monitor Performance

Watch your system resources:
- CPU usage should increase with more threads
- Memory usage: ~100-200MB per thread
- Network bandwidth: More threads = more concurrent requests

### 3. Be Respectful

- Don't use too many threads (max 8-10 recommended)
- The website may rate-limit if you're too aggressive
- Consider adding delays if you encounter rate limiting

### 4. Use Test Database

Always test with `--test-db` first:
```powershell
python run_scraper.py --site marham --limit 100 --threads 4 --test-db
```

### 5. Validate Results

After multi-threaded runs, validate the data:
```powershell
python scripts/validate_data.py --test-db
```

## Troubleshooting

### Issue: High Memory Usage

**Solution**: Reduce thread count
```powershell
# Use fewer threads
python run_scraper.py --site marham --limit 1000 --threads 2
```

### Issue: Rate Limiting / Connection Errors

**Solution**: Reduce thread count or add delays
```powershell
# Use fewer threads
python run_scraper.py --site marham --limit 1000 --threads 2
```

### Issue: Incomplete Data

**Solution**: Check logs for errors, validate data
```powershell
# Check for errors
Get-Content logs\dr_doctor_scraper.log | Select-String -Pattern "ERROR"

# Validate data
python scripts/validate_data.py --test-db
```

### Issue: Threads Not Working

**Solution**: Ensure you're using `--threads` flag and it's > 1
```powershell
# Verify threads are being used
python run_scraper.py --site marham --limit 100 --threads 4 --test-db
# Check logs for "[Thread ...]" messages
```

## Technical Details

### Thread Safety

- **MongoDB**: PyMongo is thread-safe, so multiple threads can write simultaneously
- **Statistics**: Protected with locks to prevent race conditions
- **Browser instances**: Each thread has its own Playwright browser instance

### Limitations

- **JavaScript required**: Multi-threading still requires JavaScript (buttons like "Load More" need JS)
- **Memory usage**: Each thread uses ~100-200MB of memory
- **Network bandwidth**: More threads = more concurrent network requests

### When to Use Multi-Threading

✅ **Use multi-threading when**:
- You have a good network connection
- You have sufficient system resources (CPU, RAM)
- You want to speed up large scraping jobs
- The target website can handle concurrent requests

❌ **Don't use multi-threading when**:
- You're on a slow network connection
- You have limited system resources
- The target website is rate-limiting you
- You're doing small test runs (< 10 items)

## Example Workflow

```powershell
# 1. Small test with 4 threads
python run_scraper.py --site marham --limit 10 --threads 4 --test-db

# 2. Validate results
python scripts/validate_data.py --test-db

# 3. Medium test with 4 threads
python run_scraper.py --site marham --limit 100 --threads 4 --test-db

# 4. Analyze performance
python scripts/analyze_logs.py --limit 100

# 5. Full run with 6 threads
python run_scraper.py --site marham --limit 1000 --threads 6 --test-db

# 6. Final validation
python scripts/validate_data.py --test-db
```

## Summary

Multi-threading can significantly speed up scraping by processing multiple pages/hospitals/doctors in parallel. Start with 4 threads and adjust based on your system and network capabilities. Always test with `--test-db` first and validate results after each run.

