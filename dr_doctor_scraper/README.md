# Dr.Doctor Scraper

Lightweight, production-ready scraping toolkit that collects structured
doctor and hospital data from Pakistani platforms (Marham, Oladoc) and
stores it in MongoDB for downstream usage.

Key technologies: Python 3.10+, Playwright (browser automation), BeautifulSoup,
Pydantic (models), MongoDB, and Loguru (logging).

**This README** contains quick setup, running instructions, and the new
Import/Export utilities that let contributors share/sync database snapshots.

**Workspace**: the scraper lives in `dr_doctor_scraper/` (run commands from that folder).

**Short checklist before running**:
- Python 3.10 (you already have this).
- A MongoDB instance and `MONGO_URI` set in `.env`.
- Virtual environment and dependencies installed.

---

**Quick start**

1) Create and activate venv (Windows example):

```powershell
cd dr_doctor_scraper
python -m venv .venv
.venv\\Scripts\\Activate.ps1
```

2) Install dependencies and Playwright browsers:

```powershell
pip install -r requirements.txt
playwright install
```

3) Create `.env` (copy `.env.example`) and set your `MONGO_URI`:

```powershell
copy .env.example .env
# then edit .env and set MONGO_URI
```

4) Run the scraper (examples):

```powershell
python run_scraper.py --site marham --limit 5
python run_scraper.py --site oladoc --limit 20
```

Use `--no-headless` to see the browser for debugging. Use `--limit` for quick tests.

---

**Import / Export utilities**

Two small CLI scripts are included in `scrapers/tools/` to export/import
collections for sharing/syncing DB snapshots with collaborators.

- Export hospitals to pretty JSON:

```powershell
python scrapers/tools/export_db.py --collection hospitals --out hospitals.json --format json --pretty
```

- Export hospitals to JSON-lines (one JSON per line):

```powershell
python scrapers/tools/export_db.py --collection hospitals --out hospitals.jsonl --format json
```

- Export hospitals to CSV:

```powershell
python scrapers/tools/export_db.py --collection hospitals --out hospitals.csv --format csv
```

- Import JSON-lines into hospitals (upserts by `url`):

```powershell
python scrapers/tools/import_db.py --collection hospitals --in hospitals.jsonl --format jsonl
```

Notes about running tools:
- Run from the `dr_doctor_scraper` folder. The tools are runnable directly
  (e.g. `python scrapers/tools/export_db.py ...`) — the scripts add the package
  root to `sys.path` automatically so imports work.
- Ensure `MONGO_URI` is set (in `.env` or in your PowerShell session) before
  running export/import scripts. Example for current session:

```powershell
$env:MONGO_URI = 'mongodb://localhost:27017/'
```

---

**Project layout (short)**

`scrapers/`
- `base_scraper.py` — Playwright wrapper and helpers
- `marham_scraper.py`, `oladoc_scraper.py` — site-specific scrapers
- `marham/` — Modular Marham scraper components:
  - `parsers/` — Hospital and doctor HTML parsing
  - `enrichers/` — Profile enrichment logic
  - `collectors/` — Doctor card collection with Load More handling
  - `mergers/` — Data merging and deduplication
  - `handlers/` — Hospital practice relationship management
- `database/mongo_client.py` — MongoDB wrapper (insert, upsert, indexes)
- `models/` — `DoctorModel`, `HospitalModel` (Pydantic)
- `tools/` — `export_db.py`, `import_db.py`

**Data model highlights**
- `DoctorModel` enforces cleaned fields and normalizes `fees` and `rating`.
- `HospitalModel` is used for hospital documents and enrichment.

**Troubleshooting**
- PowerShell execution policy error when activating venv:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- Module import errors when running a script by path: run from package root or
  use `python -m scrapers.tools.export_db ...` (both supported).
- If Playwright navigation fails, increase `--timeout_ms` in scraper constructor or
  run with `--no-headless` to visually debug.

---

If you want, I can add a small `scripts/` folder with a one-command PowerShell
script to export hospitals and automatically `git add` / `git commit` the
exported file (I'll not run it without your permission). If you'd like that,
tell me the filename convention you prefer (e.g. `hospitals-YYYYMMDD.jsonl`).
