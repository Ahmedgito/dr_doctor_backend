# Dr.Doctor Scraper

Production-ready, modular scraping template for collecting structured doctor data
from:

- Oladoc (https://www.oladoc.com/)
- Marham (https://www.marham.pk/)

Built with **Python**, **Playwright**, **BeautifulSoup**, **Pydantic**, **MongoDB**, and **Loguru**.

## 1. Project Purpose

Dr.Doctor recommends nearby doctors based on user symptoms and filters (fees,
location, specialty, gender, rating). This scraper populates a clean, structured
`doctors` collection in MongoDB that the backend and LLM can query.

Each document follows a unified schema so you can easily merge data from
multiple platforms.

## 2. Folder Structure

```text
dr_doctor_scraper/
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py
│   ├── oladoc_scraper.py
│   ├── marham_scraper.py
│   ├── logger.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── doctor_model.py
│   ├── database/
│   │   ├── __init__.py
│   │   └── mongo_client.py
│   └── utils/
│       ├── __init__.py
│       └── parser_helpers.py
├── run_scraper.py
├── requirements.txt
├── .env.example
└── README.md
```

## 3. Setup

### 3.1. Create environment

```bash
cd dr_doctor_scraper
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
```

## 11. Import / Export Database

Two small CLI helpers are included under `scrapers/tools/` to help export and
import collections for sharing/syncing databases.

- Export a collection to JSON-lines (default):

```powershell
python scrapers/tools/export_db.py --collection doctors --out doctors.jsonl
```

- Export to a pretty JSON array:

```powershell
python scrapers/tools/export_db.py --collection hospitals --out hospitals.json --format json --pretty
```

- Export to CSV:

```powershell
python scrapers/tools/export_db.py --collection doctors --out doctors.csv --format csv
```

- Import a JSON-lines file (upserts doctors by `profile_url`):

```powershell
python scrapers/tools/import_db.py --collection doctors --in doctors.jsonl --format jsonl
```

- Import a CSV file:

```powershell
python scrapers/tools/import_db.py --collection hospitals --in hospitals.csv --format csv
```

Notes:
- The import scripts will upsert by `profile_url` for `doctors` and by `url` for `hospitals` when possible.
- Files are expected to be either newline-delimited JSON objects (`.jsonl`), a JSON array (`.json`), or CSV.
- These tools use the project's `.env` `MONGO_URI` value via `MongoClientManager`.


```
if is gives an eror that u cant run scrips in power schell then run this comnad first 
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
then run 
```bash
.venv\Scripts\Activate.ps1
```
### 3.2. Install dependencies

```bash
pip install -r requirements.txt
playwright install
```

### 3.3. Configure environment variables

Copy the example and set your MongoDB URI:

```bash
cp .env.example .env
```

Edit `.env`:

```env
MONGO_URI=mongodb+srv://USERNAME:PASSWORD@cluster.mongodb.net/
# or local
# MONGO_URI=mongodb://localhost:27017/
```

By default, the scraper uses:

- **DB name**: `dr_doctor`
- **Collection**: `doctors`

You can also override:

- `LOG_LEVEL` (e.g. `DEBUG`, `INFO`)
- `LOG_DIR` (log file directory)

## 4. Data Model

Pydantic model (`DoctorModel`) defines the unified schema:

```python
class DoctorModel(BaseModel):
    name: str
    specialty: List[str]
    fees: Optional[int]
    city: str
    area: Optional[str]
    hospital: Optional[str]
    address: Optional[str]
    rating: Optional[float]
    experience: Optional[str]
    profile_url: str
    platform: str
    scraped_at: datetime = datetime.utcnow()
```

- `fees` is normalized to integer (e.g. "PKR 1,500" → `1500`).
- `rating` is normalized to float (e.g. "4.7/5" → `4.7`).
- `specialty` is always a list of strings.

## 5. Database Layer

`MongoClientManager` wraps MongoDB access:

- Connects using `MONGO_URI` from `.env`.
- DB: `dr_doctor`, Collection: `doctors`.
- Ensures indexes on `profile_url` (unique) and `platform`.
- Methods:
  - `doctor_exists(profile_url: str) -> bool`
  - `insert_doctor(doc: dict) -> Optional[str]`
  - `update_doctor(doc: dict) -> bool`

Each insert/update automatically adds `scraped_at` if missing.

## 6. Scrapers

### 6.1 BaseScraper

`BaseScraper` (Playwright-based) provides:

- Browser lifecycle (`with BaseScraper() as s:`)
- `load_page(url)` with retry logic
- `wait_for(selector)`
- `get_html()`
- `extract_text(selector)` helper

This base is reused by all site-specific scrapers.

### 6.2 OladocScraper

Located at `scrapers/oladoc_scraper.py`.

Responsibilities:

- Load listing page (default: `https://www.oladoc.com/doctors`).
- Extract profile URLs from listing HTML.
- Visit each profile, parse doctor fields, and validate via `DoctorModel`:
  - `name`
  - `specialty` (list)
  - `fees`
  - `city`
  - `area`
  - `hospital`
  - `address`
  - `rating`
  - `experience`
  - `profile_url`
  - `platform="oladoc"`

Selectors are written to be robust but may need fine-tuning as the site
changes.

### 6.3 MarhamScraper

Located at `scrapers/marham_scraper.py`.

Responsibilities mirror `OladocScraper`:

- Load listing page (default: `https://www.marham.pk/doctors`).
- Extract profile URLs from doctor cards.
- Visit each profile and parse the same fields, with fallback selectors.
- `platform="marham"`.

## 7. Utilities

### 7.1 parser_helpers.py

- `clean_text()` – normalize whitespace and strip.
- `extract_number()` – extract first number (int/float) from text.
- `normalize_fee()` – normalize fee strings to integer.
- `safe_get()` – safe wrapper for arbitrary getters.

### 7.2 logger.py

Configures **loguru** with:

- Console logger (colored, human-readable).
- Rotating file: `logs/dr_doctor_scraper.log`.
- Logs key events: scraper start/end, doctor extracted, duplicates skipped,
  DB insert/update success, and errors with tracebacks.

## 8. Running the Scraper

From the `dr_doctor_scraper` directory (where `run_scraper.py` lives):

```bash
python run_scraper.py --site oladoc
python run_scraper.py --site marham
python run_scraper.py --site all
```

Additional options:

- `--limit N` – limit number of profiles per site (helpful for testing).
- `--no-headless` – run browser with visible UI (for debugging).

Examples:

```bash
# Scrape first 20 doctors from Oladoc, headless
python run_scraper.py --site oladoc --limit 20

# Scrape all sites, show browser
python run_scraper.py --site all --no-headless
```

## 9. Adding New Scrapers

To add a new platform:

1. **Create a new scraper module** under `scrapers/` (e.g. `my_site_scraper.py`).
2. **Inherit from `BaseScraper`** and implement:
   - `_extract_profile_links(listing_html: str) -> List[str]`
   - `_parse_profile(profile_html: str, profile_url: str) -> DoctorModel`
   - `scrape(limit: Optional[int]) -> Dict[str, int]`
3. **Use `DoctorModel`** to enforce schema and normalization.
4. **Integrate MongoDB** via `MongoClientManager`.
5. **Update `run_scraper.py`** to add the new `--site` option.

## 10. Example Doctor Document

A stored document in `doctors` collection will look like:

```json
{
  "name": "Dr. Jane Doe",
  "specialty": ["Dermatologist", "Cosmetologist"],
  "fees": 1500,
  "city": "Lahore",
  "area": "DHA Phase 5",
  "hospital": "XYZ Hospital",
  "address": "123 Street, DHA Phase 5, Lahore",
  "rating": 4.7,
  "experience": "10 years",
  "profile_url": "https://www.oladoc.com/doctors/lahore/dr-jane-doe",
  "platform": "oladoc",
  "scraped_at": "2025-01-01T12:34:56.789Z"
}
```

---

You now have a production-ready, extensible scraping template that can be
plugged directly into your Dr.Doctor backend and LLM pipeline.
