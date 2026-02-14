# Dr.Doctor Scraper

Production-ready web scraping system for collecting structured doctor and hospital data from Pakistani healthcare platforms (Marham, Oladoc) and storing it in MongoDB.

## 🚀 Quick Start

```powershell
# 1. Setup
cd dr_doctor_scraper
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install

# 2. Configure
copy .env.example .env
# Edit .env and set MONGO_URI

# 3. Run
python run_scraper.py --site marham --threads 4 --limit 10 --test-db
```

## 📚 Documentation

**📖 [Documentation Index](DOCUMENTATION.md)** - Complete guide to all documentation

### Essential Docs
- **[API Reference](API_REFERENCE.md)** - Complete function and class documentation
- **[Commands Guide](COMMANDS.md)** - All commands, workflows, and usage examples
- **[Changelog](CHANGELOG.md)** - Complete history of all changes and improvements

### Feature Guides
- **[Testing Guide](TESTING.md)** - Testing environment and best practices
- **[Multi-threading Guide](MULTITHREADING.md)** - Parallel processing guide
- **[Step Guide](STEP_GUIDE.md)** - Step-by-step workflow execution

## 🏗️ Architecture

### Modular Structure

```
scrapers/
├── base_scraper.py              # Browser management (Playwright)
├── marham_scraper.py            # Single-threaded Marham scraper
├── marham/
│   ├── multi_threaded_scraper.py    # Multi-threaded wrapper
│   ├── parsers/                     # HTML parsing
│   │   ├── hospital_parser.py
│   │   └── doctor_parser.py
│   ├── enrichers/                   # Data enrichment
│   │   └── profile_enricher.py
│   ├── collectors/                  # Data collection
│   │   └── doctor_collector.py
│   ├── handlers/                    # Business logic
│   │   └── hospital_practice_handler.py
│   └── mergers/                     # Data merging
│       └── data_merger.py
├── crawler/                      # Web crawler module
│   ├── web_crawler.py            # Main crawler
│   ├── multi_threaded_crawler.py    # Multi-threaded crawler
│   ├── distributed_crawler.py    # Distributed crawler
│   ├── content_analyzer.py       # Content analysis
│   ├── sitemap_parser.py         # Sitemap.xml parser
│   ├── js_detector.py            # JavaScript detection
│   ├── asset_discovery.py        # Asset discovery
│   ├── site_map_generator.py     # Site map generation
│   ├── crawler_config.py         # Configuration
│   ├── utils.py                  # Utilities
│   └── run_crawler.py            # CLI entry point
├── database/
│   └── mongo_client.py          # MongoDB operations
├── models/                       # Pydantic data models
│   ├── doctor_model.py
│   ├── hospital_model.py
│   └── crawl_model.py           # Crawler models
└── utils/                        # Utility functions
    ├── url_parser.py
    └── parser_helpers.py
```

### Four-Step Workflow

1. **Step 0**: Collect all cities from hospitals page (simple HTTP requests)
2. **Step 1**: Collect hospitals from listing pages (per city)
3. **Step 2**: Enrich hospitals and collect doctor URLs
4. **Step 3**: Process and enrich doctor profiles

Each step is resumable and can be run independently.

## 🎯 Features

- ✅ **Multi-threading**: 4-8x faster with parallel processing
- ✅ **Resumable**: Continue from where you left off
- ✅ **Modular**: Reusable, testable components
- ✅ **Comprehensive**: Captures 50+ data fields per doctor/hospital
- ✅ **Bidirectional Relationships**: Doctors ↔ Hospitals with full details
- ✅ **Robust**: Error handling, retries, validation
- ✅ **Testable**: Separate test database support
- ✅ **Documented**: Complete API and command reference
- ✅ **Web Crawler**: General-purpose crawler for site mapping and content analysis

## 📊 Data Captured

### Doctors
- Basic info (name, URL, specialty, platform)
- Qualifications (institute, degree)
- Experience (years, work history)
- Services, diseases, symptoms, **interests**
- Professional statement, patient stats
- **Hospital affiliations with fees/timings** (bidirectional relationship)
- Private practice information
- Contact details

### Hospitals
- Basic info (name, URL, address, location)
- Founded year, achievements
- Clinical departments, procedures
- Facilities, support services
- Fee ranges, contact numbers
- **Doctor lists with details** (bidirectional relationship)

## 🛠️ Technologies

- **Python 3.10+**
- **Playwright** - Browser automation
- **BeautifulSoup** - HTML parsing
- **Pydantic** - Data validation
- **MongoDB** - Data storage
- **Loguru** - Logging

## 📖 Usage Examples

### Basic Scraping

```powershell
# Single-threaded
python run_scraper.py --site marham

# Multi-threaded (4 threads)
python run_scraper.py --site marham --threads 4

# With limit (testing)
python run_scraper.py --site marham --limit 100 --threads 4
```

### Step-by-Step

```powershell
# Step 0: Collect cities (no threads needed, uses HTTP requests)
python run_scraper.py --site marham --step 0

# Step 1: Collect hospitals (per city)
python run_scraper.py --site marham --threads 4 --step 1

# Step 2: Enrich hospitals
python run_scraper.py --site marham --threads 4 --step 2

# Step 3: Process doctors
python run_scraper.py --site marham --threads 4 --step 3
```

### Testing

```powershell
# Use test database
python run_scraper.py --site marham --limit 10 --test-db --threads 2

# Validate results
python scripts/validate_data.py --test-db

# Verify relationships
python scripts/verify_db_relationships.py

# Test relationships with sample data
python scripts/test_relationships.py

# Analyze performance
python scripts/analyze_logs.py --limit 10
```

### Web Crawler

The web crawler is a general-purpose tool for discovering and analyzing website content. It can:
- Discover all URLs on a website
- Create hierarchical site maps
- Analyze content types and data patterns
- Search for keywords to identify relevant pages
- Discover images, CSS, JS, and other assets
- Parse sitemap.xml files
- Detect JavaScript-rendered content

```powershell
# Single-threaded crawl
python scrapers/crawler/run_crawler.py --url https://www.marham.pk --keywords doctor,hospital

# Multi-threaded crawl (8 threads)
python scrapers/crawler/run_crawler.py --url https://www.marham.pk --threads 8 --max-depth 5

# Crawl with specific keywords and limits
python scrapers/crawler/run_crawler.py --url https://www.aku.edu --keywords doctor,physician,department --max-pages 100

# Distributed crawling (multiple instances)
python scrapers/crawler/run_crawler.py --url https://www.oladoc.com --distributed --instance-id crawler-1

# Crawl with all features disabled (faster)
python scrapers/crawler/run_crawler.py --url https://www.marham.pk --no-sitemap --no-js-detection --no-assets

# Use test database
python scrapers/crawler/run_crawler.py --url https://www.marham.pk --test-db --threads 4
```

**Crawler Options:**
- `--url`: Starting URL(s), comma-separated for multiple URLs
- `--keywords`: Keywords to search for, comma-separated
- `--max-depth`: Maximum crawl depth (default: unlimited)
- `--max-pages`: Maximum number of pages to crawl (default: unlimited)
- `--threads`: Number of threads for parallel crawling (default: 1)
- `--distributed`: Enable distributed crawling mode
- `--instance-id`: Instance ID for distributed crawling
- `--no-sitemap`: Disable sitemap.xml parsing
- `--no-js-detection`: Disable JavaScript rendering detection
- `--no-assets`: Disable asset discovery
- `--no-robots`: Don't respect robots.txt
- `--delay`: Delay between requests in seconds (default: 0.5)
- `--headless`: Run browser in headless mode (default: True)
- `--no-headless`: Run browser with visible UI
- `--test-db`: Use test database

**Crawler Output:**
- All discovered pages stored in `crawled_pages` collection
- Site maps stored in `site_maps` collection
- Assets stored in `crawled_assets` collection
- Each page includes: URL, title, depth, content type, keywords found, links, assets

## 🔧 Scripts

- `run_scraper.py` - Main scraper entry point
- `scrapers/crawler/run_crawler.py` - Web crawler entry point
- `scripts/analyze_logs.py` - Log analysis and statistics
- `scripts/validate_data.py` - Data validation
- `scripts/export_and_clear_db.py` - Database export
- `scripts/log_diagnostics.py` - Detailed log diagnostics
- `scripts/verify_db_relationships.py` - Verify doctor-hospital bidirectional relationships
- `scripts/test_relationships.py` - Test relationships with sample data

## 📝 Project Status

**Current Phase**: Phase 1 - Scraper Refinement & Testing ✅

See [Project Roadmap](../README.md#project-roadmap) for full development plan.

## 🤝 Contributing

1. Use test database for development: `--test-db`
2. Run validation after changes: `python scripts/validate_data.py --test-db`
3. Check logs for issues: `python scripts/log_diagnostics.py`
4. Follow modular architecture patterns

## 📄 License

[Your License Here]

## 🔗 Links

- [API Reference](API_REFERENCE.md)
- [Commands Guide](COMMANDS.md)
- [Changelog](CHANGELOG.md)
