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
├── database/
│   └── mongo_client.py          # MongoDB operations
├── models/                       # Pydantic data models
│   ├── doctor_model.py
│   └── hospital_model.py
└── utils/                        # Utility functions
    ├── url_parser.py
    └── parser_helpers.py
```

### Three-Step Workflow

1. **Step 1**: Collect hospitals from listing pages
2. **Step 2**: Enrich hospitals and collect doctor URLs
3. **Step 3**: Process and enrich doctor profiles

Each step is resumable and can be run independently.

## 🎯 Features

- ✅ **Multi-threading**: 4-8x faster with parallel processing
- ✅ **Resumable**: Continue from where you left off
- ✅ **Modular**: Reusable, testable components
- ✅ **Comprehensive**: Captures 50+ data fields per doctor/hospital
- ✅ **Robust**: Error handling, retries, validation
- ✅ **Testable**: Separate test database support
- ✅ **Documented**: Complete API and command reference

## 📊 Data Captured

### Doctors
- Basic info (name, URL, specialty, platform)
- Qualifications (institute, degree)
- Experience (years, work history)
- Services, diseases, symptoms
- Professional statement, patient stats
- Hospital affiliations with fees/timings
- Private practice information
- Contact details

### Hospitals
- Basic info (name, URL, address, location)
- Founded year, achievements
- Clinical departments, procedures
- Facilities, support services
- Fee ranges, contact numbers
- Doctor lists with details

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
# Step 1: Collect hospitals
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

# Analyze performance
python scripts/analyze_logs.py --limit 10
```

## 🔧 Scripts

- `run_scraper.py` - Main scraper entry point
- `scripts/analyze_logs.py` - Log analysis and statistics
- `scripts/validate_data.py` - Data validation
- `scripts/export_and_clear_db.py` - Database export
- `scripts/log_diagnostics.py` - Detailed log diagnostics

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
