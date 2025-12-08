"""Detailed log diagnostics for the most recent scraper run."""

import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List

from loguru import logger


def analyze_last_run(log_path: Path) -> Dict:
    """Analyze the most recent scraper run in detail."""
    
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the last "Starting scraper" line
    last_start_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if "Starting scraper" in lines[i]:
            last_start_idx = i
            break
    
    if last_start_idx is None:
        return {"error": "No scraper start found in logs"}
    
    # Extract timestamp from start line
    start_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', lines[last_start_idx])
    if not start_match:
        return {"error": "Could not parse start timestamp"}
    
    start_time = datetime.strptime(start_match.group(1), '%Y-%m-%d %H:%M:%S')
    
    # Analyze from start to end
    run_lines = lines[last_start_idx:]
    
    diagnostics = {
        "start_time": start_time.isoformat(),
        "total_lines": len(run_lines),
        "errors": [],
        "warnings": [],
        "timeouts": [],
        "thread_stats": defaultdict(lambda: {"doctors": 0, "errors": 0, "warnings": 0}),
        "step_times": {},
        "error_types": Counter(),
        "timeout_urls": [],
        "summary": {},
    }
    
    current_step = None
    step_start_time = None
    
    for line in run_lines:
        # Extract timestamp
        time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if time_match:
            line_time = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
        
        # Track steps
        if "Step 1:" in line or "Step 1 complete" in line:
            if "Step 1:" in line and current_step != "Step 1":
                if step_start_time and current_step:
                    diagnostics["step_times"][current_step] = (line_time - step_start_time).total_seconds()
                current_step = "Step 1"
                step_start_time = line_time
        elif "Step 2:" in line or "Step 2 complete" in line:
            if "Step 2:" in line and current_step != "Step 2":
                if step_start_time and current_step:
                    diagnostics["step_times"][current_step] = (line_time - step_start_time).total_seconds()
                current_step = "Step 2"
                step_start_time = line_time
        elif "Step 3:" in line or "Step 3 complete" in line:
            if "Step 3:" in line and current_step != "Step 3":
                if step_start_time and current_step:
                    diagnostics["step_times"][current_step] = (line_time - step_start_time).total_seconds()
                current_step = "Step 3"
                step_start_time = line_time
        
        # Track errors
        if "ERROR" in line:
            diagnostics["errors"].append(line.strip())
            # Extract error type
            if "Timeout" in line:
                diagnostics["error_types"]["Timeout"] += 1
                # Extract URL from timeout
                url_match = re.search(r'load_page:\s*(https?://[^\s\)]+)', line)
                if url_match:
                    diagnostics["timeout_urls"].append(url_match.group(1))
            elif "failed after" in line:
                diagnostics["error_types"]["Failed after retries"] += 1
            else:
                diagnostics["error_types"]["Other"] += 1
        
        # Track warnings
        if "WARNING" in line:
            diagnostics["warnings"].append(line.strip())
            if "Timeout" in line:
                diagnostics["timeouts"].append(line.strip())
        
        # Track thread statistics
        thread_match = re.search(r'\[Thread (\d+)\]', line)
        if thread_match:
            thread_id = thread_match.group(1)
            if "ERROR" in line:
                diagnostics["thread_stats"][thread_id]["errors"] += 1
            if "WARNING" in line:
                diagnostics["thread_stats"][thread_id]["warnings"] += 1
            if "completed:" in line and "doctors" in line:
                doc_match = re.search(r'completed:\s*(\d+)\s*doctors', line)
                if doc_match:
                    diagnostics["thread_stats"][thread_id]["doctors"] += int(doc_match.group(1))
        
        # Extract summary from final completion message
        if "Multi-threaded scraping complete" in line or "Scraping finished" in line:
            # Extract stats
            stats_match = re.search(r'total=(\d+).*hospitals=(\d+).*doctors=(\d+).*inserted=(\d+).*updated=(\d+).*skipped=(\d+).*errors=(\d+)', line)
            if stats_match:
                diagnostics["summary"] = {
                    "total": int(stats_match.group(1)),
                    "hospitals": int(stats_match.group(2)),
                    "doctors": int(stats_match.group(3)),
                    "inserted": int(stats_match.group(4)),
                    "updated": int(stats_match.group(5)),
                    "skipped": int(stats_match.group(6)),
                    "errors": int(stats_match.group(7)),
                }
            # Calculate end time
            if time_match:
                end_time = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                diagnostics["end_time"] = end_time.isoformat()
                diagnostics["duration_seconds"] = (end_time - start_time).total_seconds()
                diagnostics["duration_minutes"] = diagnostics["duration_seconds"] / 60
    
    # Finalize last step time
    if step_start_time and current_step:
        if "end_time" in diagnostics:
            end_time = datetime.fromisoformat(diagnostics["end_time"])
            diagnostics["step_times"][current_step] = (end_time - step_start_time).total_seconds()
    
    return diagnostics


def print_diagnostics(diagnostics: Dict):
    """Print formatted diagnostics report."""
    
    if "error" in diagnostics:
        print(f"Error: {diagnostics['error']}")
        return
    
    print("\n" + "="*80)
    print("DETAILED LOG DIAGNOSTICS - LAST RUN")
    print("="*80)
    
    # Summary
    print(f"\n{'='*80}")
    print("RUN SUMMARY")
    print(f"{'='*80}")
    if "start_time" in diagnostics:
        print(f"Start Time: {diagnostics['start_time']}")
    if "end_time" in diagnostics:
        print(f"End Time: {diagnostics['end_time']}")
    if "duration_minutes" in diagnostics:
        print(f"Duration: {diagnostics['duration_minutes']:.2f} minutes ({diagnostics['duration_seconds']:.2f} seconds)")
    if "summary" in diagnostics and diagnostics["summary"]:
        s = diagnostics["summary"]
        print(f"\nResults:")
        print(f"  Total Items: {s.get('total', 0)}")
        print(f"  Hospitals: {s.get('hospitals', 0)}")
        print(f"  Doctors: {s.get('doctors', 0)}")
        print(f"  Inserted: {s.get('inserted', 0)}")
        print(f"  Updated: {s.get('updated', 0)}")
        print(f"  Skipped: {s.get('skipped', 0)}")
        print(f"  Errors: {s.get('errors', 0)}")
    
    # Step Times
    if diagnostics["step_times"]:
        print(f"\n{'='*80}")
        print("STEP TIMING")
        print(f"{'='*80}")
        for step, time_sec in diagnostics["step_times"].items():
            print(f"{step}: {time_sec:.2f} seconds ({time_sec/60:.2f} minutes)")
    
    # Error Analysis
    print(f"\n{'='*80}")
    print("ERROR ANALYSIS")
    print(f"{'='*80}")
    print(f"Total Errors: {len(diagnostics['errors'])}")
    print(f"Total Warnings: {len(diagnostics['warnings'])}")
    print(f"Total Timeouts: {len(diagnostics['timeouts'])}")
    
    if diagnostics["error_types"]:
        print(f"\nError Types:")
        for error_type, count in diagnostics["error_types"].most_common():
            print(f"  {error_type}: {count}")
    
    # Timeout URLs (sample)
    if diagnostics["timeout_urls"]:
        print(f"\nTimeout URLs (showing first 10):")
        for url in diagnostics["timeout_urls"][:10]:
            print(f"  - {url}")
        if len(diagnostics["timeout_urls"]) > 10:
            print(f"  ... and {len(diagnostics['timeout_urls']) - 10} more")
    
    # Thread Statistics
    if diagnostics["thread_stats"]:
        print(f"\n{'='*80}")
        print("THREAD STATISTICS")
        print(f"{'='*80}")
        total_doctors = 0
        total_errors = 0
        total_warnings = 0
        
        for thread_id, stats in sorted(diagnostics["thread_stats"].items()):
            doctors = stats["doctors"]
            errors = stats["errors"]
            warnings = stats["warnings"]
            total_doctors += doctors
            total_errors += errors
            total_warnings += warnings
            print(f"Thread {thread_id}:")
            print(f"  Doctors Processed: {doctors}")
            print(f"  Errors: {errors}")
            print(f"  Warnings: {warnings}")
        
        print(f"\nThread Totals:")
        print(f"  Total Doctors: {total_doctors}")
        print(f"  Total Errors: {total_errors}")
        print(f"  Total Warnings: {total_warnings}")
        if len(diagnostics["thread_stats"]) > 0:
            print(f"  Average Doctors per Thread: {total_doctors / len(diagnostics['thread_stats']):.1f}")
    
    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")
    
    if len(diagnostics["timeouts"]) > 50:
        print("⚠ High number of timeouts detected:")
        print("  - Consider increasing timeout_ms in base_scraper.py")
        print("  - Check network connection stability")
        print("  - Reduce number of threads if rate-limited")
    
    if diagnostics["error_types"].get("Timeout", 0) > 100:
        print("⚠ Many timeout errors:")
        print("  - Website may be slow or rate-limiting")
        print("  - Consider reducing thread count")
        print("  - Add delays between requests")
    
    if diagnostics["thread_stats"]:
        thread_loads = [s["doctors"] for s in diagnostics["thread_stats"].values()]
        if thread_loads:
            max_load = max(thread_loads)
            min_load = min(thread_loads)
            if max_load - min_load > 50:
                print("⚠ Uneven thread distribution:")
                print(f"  - Max load: {max_load}, Min load: {min_load}")
                print("  - Consider adjusting work distribution algorithm")
    
    if diagnostics["summary"] and diagnostics["summary"].get("errors", 0) > 0:
        error_rate = diagnostics["summary"]["errors"] / max(diagnostics["summary"].get("total", 1), 1) * 100
        if error_rate > 5:
            print(f"⚠ High error rate: {error_rate:.1f}%")
            print("  - Review error logs for patterns")
            print("  - Check if website structure has changed")
    
    print("\n" + "="*80)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Detailed log diagnostics for last run")
    parser.add_argument("--log-file", type=str, default="logs/dr_doctor_scraper.log", help="Path to log file")
    args = parser.parse_args()
    
    log_path = Path(args.log_file)
    if not log_path.exists():
        logger.error(f"Log file not found: {log_path}")
        return
    
    logger.info(f"Analyzing last run in: {log_path}")
    diagnostics = analyze_last_run(log_path)
    print_diagnostics(diagnostics)


if __name__ == "__main__":
    main()

