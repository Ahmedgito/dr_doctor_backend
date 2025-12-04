# Dr.Doctor Backend

A web scraping system for collecting doctor and hospital data from Pakistani healthcare platforms (Marham, Oladoc) and storing it in MongoDB for downstream processing.

## Project Overview

This project is part of a larger system that:
- Scrapes doctor and hospital data from multiple Pakistani healthcare platforms
- Stores structured data in MongoDB
- Supports location-based data collection and enrichment
- Provides data export/import utilities for collaboration

## Project Structure

```
dr_doctor_backend/
├── dr_doctor_scraper/          # Main scraper package
│   ├── scrapers/               # Scraper implementations
│   │   ├── base_scraper.py    # Base scraper with Playwright wrapper
│   │   ├── marham_scraper.py  # Marham platform scraper
│   │   ├── oladoc_scraper.py  # Oladoc platform scraper
│   │   ├── models/            # Pydantic data models
│   │   ├── database/          # MongoDB client wrapper
│   │   ├── utils/             # Utility functions
│   │   └── tools/             # Export/import utilities
│   ├── run_scraper.py         # Main entry point
│   ├── requirements.txt       # Python dependencies
│   └── README.md              # Detailed scraper documentation
├── mongo_test.py              # MongoDB connection test script
└── README.md                  # This file
```

## Quick Start

1. **Navigate to the scraper directory:**
   ```powershell
   cd dr_doctor_scraper
   ```

2. **Set up virtual environment:**
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   playwright install
   ```

4. **Configure environment:**
   - Copy `.env.example` to `.env` (if it exists)
   - Set `MONGO_URI` in `.env` file

5. **Run the scraper:**
   ```powershell
   python run_scraper.py --site marham --limit 5
   ```

For detailed documentation, see [dr_doctor_scraper/README.md](dr_doctor_scraper/README.md).

## Technologies

- **Python 3.10+**
- **Playwright** - Browser automation
- **BeautifulSoup** - HTML parsing
- **Pydantic** - Data validation and models
- **MongoDB** - Data storage
- **Loguru** - Logging

## Development Status

- ✅ Marham scraper (hospital-first approach)
- ✅ Oladoc scraper (basic implementation)
- ✅ MongoDB integration with upsert support
- ✅ Data export/import utilities
- 🔄 Additional platform scrapers (planned)
- 🔄 Data deduplication and merging (in progress)

## Notes

- The scraper uses a hospital-first approach for Marham, collecting hospitals first then doctors within each hospital
- Data is stored in MongoDB with unique indexes on `profile_url` (doctors) and `name+address` (hospitals)
- Export/import tools are available in `scrapers/tools/` for sharing database snapshots
