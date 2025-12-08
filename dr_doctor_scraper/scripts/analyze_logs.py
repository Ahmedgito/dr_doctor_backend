"""Analyze scraper logs to extract statistics and performance metrics."""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

from loguru import logger


def parse_log_file(log_path: Path) -> List[Dict]:
    """Parse log file and extract run information."""
    runs = []
    current_run = None
    
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Match "Starting scraper with args"
            match = re.search(r'Starting scraper with args:.*limit=(\d+)', line)
            if match:
                if current_run:
                    runs.append(current_run)
                current_run = {
                    'limit': int(match.group(1)),
                    'start_time': None,
                    'end_time': None,
                    'start_line': None,
                    'hospitals_collected': 0,
                    'hospitals_enriched': 0,
                    'doctors_collected': 0,
                    'doctors_processed': 0,
                    'pages_scraped': 0,
                    'errors': [],
                    'step1_time': None,
                    'step2_time': None,
                    'step3_time': None,
                }
                # Extract timestamp
                time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                if time_match:
                    current_run['start_time'] = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
                    current_run['start_line'] = line
            
            if not current_run:
                continue
            
            # Extract timestamps
            time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if time_match:
                current_run['end_time'] = datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S')
            
            # Step 1 completion
            if 'Step 1 complete:' in line:
                match = re.search(r'Step 1 complete: (\d+) hospitals', line)
                if match:
                    current_run['hospitals_collected'] = int(match.group(1))
                    if time_match:
                        if current_run['start_time']:
                            current_run['step1_time'] = (current_run['end_time'] - current_run['start_time']).total_seconds()
            
            # Step 2 completion
            if 'Step 2 complete:' in line:
                match = re.search(r'Step 2 complete: Hospitals enriched', line)
                if match and time_match and current_run['start_time']:
                    step1_end = current_run['start_time']
                    if current_run['step1_time']:
                        step1_end = current_run['start_time'] + timedelta(seconds=current_run['step1_time'])
                    current_run['step2_time'] = (current_run['end_time'] - step1_end).total_seconds()
            
            # Step 3 completion
            if 'Step 3 complete:' in line:
                match = re.search(r'Step 3 complete: (\d+) doctors', line)
                if match:
                    current_run['doctors_processed'] = int(match.group(1))
                    if time_match:
                        step2_end = current_run['start_time']
                        if current_run['step1_time']:
                            step2_end += timedelta(seconds=current_run['step1_time'])
                        if current_run['step2_time']:
                            step2_end += timedelta(seconds=current_run['step2_time'])
                        current_run['step3_time'] = (current_run['end_time'] - step2_end).total_seconds()
            
            # Count pages scraped (Loading page:)
            if 'Loading page:' in line and 'hospitals/karachi?page=' in line:
                current_run['pages_scraped'] += 1
            
            # Count hospitals enriched
            if 'Enriched hospital:' in line:
                current_run['hospitals_enriched'] += 1
            
            # Count doctors collected
            if 'Updated hospital' in line and 'doctors' in line:
                match = re.search(r'with (\d+) doctors', line)
                if match:
                    current_run['doctors_collected'] += int(match.group(1))
            
            # Track errors
            if 'ERROR' in line or 'WARNING' in line:
                current_run['errors'].append(line.strip())
        
        if current_run:
            runs.append(current_run)
    
    return runs


def calculate_stats(runs: List[Dict]) -> Dict:
    """Calculate aggregate statistics from runs."""
    if not runs:
        return {}
    
    stats = {
        'total_runs': len(runs),
        'runs_by_limit': defaultdict(list),
        'total_hospitals_collected': 0,
        'total_hospitals_enriched': 0,
        'total_doctors_collected': 0,
        'total_doctors_processed': 0,
        'total_pages_scraped': 0,
        'total_errors': 0,
        'avg_step1_time': 0,
        'avg_step2_time': 0,
        'avg_step3_time': 0,
        'avg_total_time': 0,
        'avg_hospitals_per_page': 0,
        'avg_time_per_hospital': 0,
        'avg_time_per_doctor': 0,
    }
    
    step1_times = []
    step2_times = []
    step3_times = []
    total_times = []
    
    for run in runs:
        limit = run.get('limit', 0)
        stats['runs_by_limit'][limit].append(run)
        stats['total_hospitals_collected'] += run.get('hospitals_collected', 0)
        stats['total_hospitals_enriched'] += run.get('hospitals_enriched', 0)
        stats['total_doctors_collected'] += run.get('doctors_collected', 0)
        stats['total_doctors_processed'] += run.get('doctors_processed', 0)
        stats['total_pages_scraped'] += run.get('pages_scraped', 0)
        stats['total_errors'] += len(run.get('errors', []))
        
        if run.get('step1_time'):
            step1_times.append(run['step1_time'])
        if run.get('step2_time'):
            step2_times.append(run['step2_time'])
        if run.get('step3_time'):
            step3_times.append(run['step3_time'])
        
        if run.get('start_time') and run.get('end_time'):
            total_time = (run['end_time'] - run['start_time']).total_seconds()
            total_times.append(total_time)
    
    if step1_times:
        stats['avg_step1_time'] = sum(step1_times) / len(step1_times)
    if step2_times:
        stats['avg_step2_time'] = sum(step2_times) / len(step2_times)
    if step3_times:
        stats['avg_step3_time'] = sum(step3_times) / len(step3_times)
    if total_times:
        stats['avg_total_time'] = sum(total_times) / len(total_times)
    
    if stats['total_pages_scraped'] > 0:
        stats['avg_hospitals_per_page'] = stats['total_hospitals_collected'] / stats['total_pages_scraped']
    
    if stats['total_hospitals_enriched'] > 0:
        stats['avg_time_per_hospital'] = stats['avg_step2_time'] / stats['total_hospitals_enriched'] if stats['avg_step2_time'] > 0 else 0
    
    if stats['total_doctors_processed'] > 0:
        stats['avg_time_per_doctor'] = stats['avg_step3_time'] / stats['total_doctors_processed'] if stats['avg_step3_time'] > 0 else 0
    
    return stats


def print_report(runs: List[Dict], stats: Dict):
    """Print a formatted report."""
    print("\n" + "="*80)
    print("SCRAPER LOG ANALYSIS REPORT")
    print("="*80)
    
    print(f"\nTotal Runs Analyzed: {stats['total_runs']}")
    print(f"\nRuns by Limit:")
    for limit, limit_runs in stats['runs_by_limit'].items():
        print(f"  Limit {limit}: {len(limit_runs)} run(s)")
    
    print(f"\n{'='*80}")
    print("AGGREGATE STATISTICS")
    print(f"{'='*80}")
    print(f"Total Hospitals Collected: {stats['total_hospitals_collected']}")
    print(f"Total Hospitals Enriched: {stats['total_hospitals_enriched']}")
    print(f"Total Doctors Collected: {stats['total_doctors_collected']}")
    print(f"Total Doctors Processed: {stats['total_doctors_processed']}")
    print(f"Total Pages Scraped: {stats['total_pages_scraped']}")
    print(f"Total Errors: {stats['total_errors']}")
    
    print(f"\n{'='*80}")
    print("PERFORMANCE METRICS")
    print(f"{'='*80}")
    print(f"Average Step 1 Time (Collection): {stats['avg_step1_time']:.2f} seconds")
    print(f"Average Step 2 Time (Enrichment): {stats['avg_step2_time']:.2f} seconds")
    print(f"Average Step 3 Time (Processing): {stats['avg_step3_time']:.2f} seconds")
    print(f"Average Total Time: {stats['avg_total_time']:.2f} seconds ({stats['avg_total_time']/60:.2f} minutes)")
    print(f"Average Hospitals per Page: {stats['avg_hospitals_per_page']:.2f}")
    print(f"Average Time per Hospital: {stats['avg_time_per_hospital']:.2f} seconds")
    print(f"Average Time per Doctor: {stats['avg_time_per_doctor']:.2f} seconds")
    
    # Detailed run information
    print(f"\n{'='*80}")
    print("DETAILED RUN INFORMATION")
    print(f"{'='*80}")
    for i, run in enumerate(runs, 1):
        print(f"\nRun #{i} (Limit: {run.get('limit', 'N/A')})")
        if run.get('start_time'):
            print(f"  Start Time: {run['start_time']}")
        if run.get('end_time'):
            print(f"  End Time: {run['end_time']}")
        if run.get('start_time') and run.get('end_time'):
            duration = (run['end_time'] - run['start_time']).total_seconds()
            print(f"  Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)")
        print(f"  Hospitals Collected: {run.get('hospitals_collected', 0)}")
        print(f"  Hospitals Enriched: {run.get('hospitals_enriched', 0)}")
        print(f"  Doctors Collected: {run.get('doctors_collected', 0)}")
        print(f"  Doctors Processed: {run.get('doctors_processed', 0)}")
        print(f"  Pages Scraped: {run.get('pages_scraped', 0)}")
        print(f"  Errors: {len(run.get('errors', []))}")
        if run.get('step1_time'):
            print(f"  Step 1 Time: {run['step1_time']:.2f} seconds")
        if run.get('step2_time'):
            print(f"  Step 2 Time: {run['step2_time']:.2f} seconds")
        if run.get('step3_time'):
            print(f"  Step 3 Time: {run['step3_time']:.2f} seconds")


def main():
    """Main entry point."""
    import argparse
    from datetime import timedelta
    
    parser = argparse.ArgumentParser(description="Analyze scraper logs")
    parser.add_argument("--log-file", type=str, default="logs/dr_doctor_scraper.log", help="Path to log file")
    parser.add_argument("--limit", type=int, help="Filter runs by limit value")
    args = parser.parse_args()
    
    log_path = Path(args.log_file)
    if not log_path.exists():
        logger.error(f"Log file not found: {log_path}")
        return
    
    logger.info(f"Analyzing log file: {log_path}")
    runs = parse_log_file(log_path)
    
    if args.limit:
        runs = [r for r in runs if r.get('limit') == args.limit]
        logger.info(f"Filtered to {len(runs)} runs with limit={args.limit}")
    
    if not runs:
        logger.warning("No runs found in log file")
        return
    
    stats = calculate_stats(runs)
    print_report(runs, stats)


if __name__ == "__main__":
    main()

