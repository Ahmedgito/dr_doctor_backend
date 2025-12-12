# API Reference - Complete Function Documentation

This document provides comprehensive documentation for every function, class, and method in the Dr.Doctor Scraper codebase.

## Table of Contents

1. [Core Scrapers](#core-scrapers)
2. [Database Management](#database-management)
3. [Parsers](#parsers)
4. [Enrichers](#enrichers)
5. [Collectors](#collectors)
6. [Handlers](#handlers)
7. [Mergers](#mergers)
8. [Utilities](#utilities)
9. [Models](#models)
10. [Scripts](#scripts)

---

## Core Scrapers

### `BaseScraper` (`scrapers/base_scraper.py`)

Base class for all scrapers providing Playwright browser management and common functionality.

#### `__init__(headless=True, timeout_ms=15000, max_retries=3, wait_between_retries=2.0, disable_js=False)`

Initialize the base scraper.

**Parameters:**
- `headless` (bool): Run browser in headless mode (default: True)
- `timeout_ms` (int): Page load timeout in milliseconds (default: 15000)
- `max_retries` (int): Maximum retries for failed operations (default: 3)
- `wait_between_retries` (float): Seconds to wait between retries (default: 2.0)
- `disable_js` (bool): Disable JavaScript for faster scraping (default: False)

**Returns:** None

#### `__enter__() -> BaseScraper`

Context manager entry. Starts Playwright browser.

**Returns:** Self (BaseScraper instance)

#### `__exit__(exc_type, exc_val, exc_tb) -> None`

Context manager exit. Closes Playwright browser and cleans up resources.

**Parameters:**
- `exc_type`: Exception type
- `exc_val`: Exception value
- `exc_tb`: Exception traceback

**Returns:** None

#### `load_page(url: str) -> None`

Navigate to a URL with retry logic.

**Parameters:**
- `url` (str): URL to load

**Raises:** RuntimeError if page not initialized

**Returns:** None

#### `wait_for(selector: str, timeout_ms: Optional[int] = None) -> None`

Wait for a CSS selector to appear on the page.

**Parameters:**
- `selector` (str): CSS selector to wait for
- `timeout_ms` (Optional[int]): Timeout in milliseconds (default: uses instance timeout)

**Raises:** RuntimeError if page not initialized

**Returns:** None

#### `get_html() -> str`

Get the current page HTML content.

**Raises:** RuntimeError if page not initialized

**Returns:** (str) HTML content of current page

#### `extract_text(selector: str) -> Optional[str]`

Safely extract text from a CSS selector.

**Parameters:**
- `selector` (str): CSS selector

**Returns:** (Optional[str]) Extracted text or None if not found

---

### `MarhamScraper` (`scrapers/marham_scraper.py`)

Single-threaded Marham scraper using modular components.

#### `__init__(mongo_client, hospitals_listing_url=HOSPITALS_LISTING, headless=True, timeout_ms=15000, max_retries=3, disable_js=False)`

Initialize Marham scraper.

**Parameters:**
- `mongo_client` (MongoClientManager): MongoDB client manager
- `hospitals_listing_url` (str): Base URL for hospital listings
- `headless` (bool): Run browser in headless mode
- `timeout_ms` (int): Page load timeout
- `max_retries` (int): Maximum retries
- `disable_js` (bool): Disable JavaScript

**Returns:** None

#### `scrape(limit: Optional[int] = None, step: Optional[int] = None) -> Dict[str, int]`

Run the complete scraping workflow (all 4 steps) or a specific step.

**Parameters:**
- `limit` (Optional[int]): Maximum number of hospitals to process (None = no limit)
- `step` (Optional[int]): Run only specific step (0, 1, 2, or 3). None = run all steps

**Returns:** (Dict[str, int]) Statistics dictionary with keys: total, inserted, skipped, hospitals, updated, doctors, cities

---

### `MultiThreadedMarhamScraper` (`scrapers/marham/multi_threaded_scraper.py`)

Multi-threaded wrapper for Marham scraper.

#### `__init__(mongo_client, num_threads=4, headless=True, timeout_ms=15000, max_retries=3)`

Initialize multi-threaded scraper.

**Parameters:**
- `mongo_client` (MongoClientManager): MongoDB client manager
- `num_threads` (int): Number of worker threads (default: 4)
- `headless` (bool): Run browsers in headless mode
- `timeout_ms` (int): Page load timeout
- `max_retries` (int): Maximum retries

**Returns:** None

#### `scrape(limit: Optional[int] = None, max_pages=500, step: Optional[int] = None) -> Dict[str, int]`

Run multi-threaded scraping workflow.

**Parameters:**
- `limit` (Optional[int]): Maximum hospitals to process
- `max_pages` (int): Maximum listing pages to check (default: 500)
- `step` (Optional[int]): Run only specific step (1, 2, or 3). None = all steps

**Returns:** (Dict[str, int]) Statistics dictionary

---

## Database Management

### `MongoClientManager` (`scrapers/database/mongo_client.py`)

Manages MongoDB connections and provides CRUD operations.

#### `__init__(test_db=False)`

Initialize MongoDB client manager.

**Parameters:**
- `test_db` (bool): Use test database (dr_doctor_test) instead of production

**Raises:** ValueError if MONGO_URI missing

**Returns:** None

#### `doctor_exists(url: str) -> bool`

Check if doctor exists by profile URL.

**Parameters:**
- `url` (str): Doctor profile URL

**Returns:** (bool) True if doctor exists

#### `insert_doctor(doc: Dict) -> Optional[str]`

Insert a doctor document.

**Parameters:**
- `doc` (Dict): Doctor document dictionary

**Returns:** (Optional[str]) Inserted document ID or None on failure

#### `upsert_minimal_doctor(profile_url: str, name: str, hospital_url: Optional[str] = None) -> bool`

Insert or update minimal doctor record (name + profile_url only).

**Parameters:**
- `profile_url` (str): Doctor profile URL
- `name` (str): Doctor name
- `hospital_url` (Optional[str]): Hospital URL where doctor was found

**Returns:** (bool) True on success

#### `hospital_exists(name: str, address: str) -> bool`

Check if hospital exists by name and address.

**Parameters:**
- `name` (str): Hospital name
- `address` (str): Hospital address

**Returns:** (bool) True if hospital exists

#### `insert_hospital(doc: Dict) -> Optional[str]`

Insert a hospital document.

**Parameters:**
- `doc` (Dict): Hospital document dictionary

**Returns:** (Optional[str]) Inserted document ID or None on failure

#### `update_hospital(url: Optional[str], doc: Dict) -> bool`

Update hospital document by URL or name+address.

**Parameters:**
- `url` (Optional[str]): Hospital URL
- `doc` (Dict): Hospital document dictionary

**Returns:** (bool) True on success

#### `get_hospitals_needing_enrichment(limit: Optional[int] = None)`

Get hospitals that need enrichment (status='pending' or missing).

**Parameters:**
- `limit` (Optional[int]): Maximum number to return

**Returns:** MongoDB cursor

#### `get_hospitals_needing_doctor_collection(limit: Optional[int] = None)`

Get hospitals that need doctor collection.

**Parameters:**
- `limit` (Optional[int]): Maximum number to return

**Returns:** MongoDB cursor

#### `get_doctors_needing_processing(limit: Optional[int] = None)`

Get doctors that need full processing.

**Parameters:**
- `limit` (Optional[int]): Maximum number to return

**Returns:** MongoDB cursor

#### `update_doctor_status(profile_url: str, status: str) -> bool`

Update doctor's scrape status.

**Parameters:**
- `profile_url` (str): Doctor profile URL
- `status` (str): New status ('pending', 'processed', etc.)

**Returns:** (bool) True on success

#### `update_hospital_status(url: str, status: str) -> bool`

Update hospital's scrape status.

**Parameters:**
- `url` (str): Hospital URL
- `status` (str): New status

**Returns:** (bool) True on success

#### `city_exists(url: str) -> bool`

Check if city exists by URL.

**Parameters:**
- `url` (str): City URL

**Returns:** (bool) True if city exists

#### `upsert_city(name: str, url: str) -> bool`

Insert or update a city record.

**Parameters:**
- `name` (str): City name
- `url` (str): City URL (format: https://www.marham.pk/hospitals/{city})

**Returns:** (bool) True on success

#### `get_cities_needing_scraping(limit: Optional[int] = None)`

Get cities that need scraping (status is 'pending' or missing).

**Parameters:**
- `limit` (Optional[int]): Maximum number to return

**Returns:** MongoDB cursor

#### `update_city_status(url: str, status: str) -> bool`

Update city's scrape status.

**Parameters:**
- `url` (str): City URL
- `status` (str): New status ('pending', 'scraped')

**Returns:** (bool) True on success

#### `close() -> None`

Close MongoDB client connection.

**Returns:** None

---

## Parsers

### `HospitalParser` (`scrapers/marham/parsers/hospital_parser.py`)

Parses hospital data from HTML.

#### `parse_hospital_cards(html: str) -> List[dict]`

Parse hospital cards from listing page HTML.

**Parameters:**
- `html` (str): HTML content of listing page

**Returns:** (List[dict]) List of hospital dictionaries with name, city, area, address, url

#### `parse_full_hospital(html: str, url: str) -> dict`

Parse hospital detail page to extract comprehensive information.

**Parameters:**
- `html` (str): HTML content of hospital page
- `url` (str): Hospital URL

**Returns:** (dict) Dictionary with enriched hospital data

#### `extract_location_from_card(page: Page, hospital_url: str) -> Optional[Dict[str, float]]`

Extract location (lat/lng) from hospital card's "View Directions" button.

**Parameters:**
- `page` (Page): Playwright page object
- `hospital_url` (str): Hospital URL

**Returns:** (Optional[Dict[str, float]]) Dictionary with 'lat' and 'lng' keys, or None

---

### `DoctorParser` (`scrapers/marham/parsers/doctor_parser.py`)

Parses doctor data from HTML.

#### `parse_doctor_card(card: BeautifulSoup, hospital_url: str) -> Optional[DoctorModel]`

Parse a single doctor card element.

**Parameters:**
- `card` (BeautifulSoup): BeautifulSoup Tag object representing doctor card
- `hospital_url` (str): URL of hospital where doctor was found

**Returns:** (Optional[DoctorModel]) DoctorModel instance or None if parsing fails

#### `extract_doctors_from_list(html: str, hospital_url: str) -> List[dict]`

Extract doctor names and URLs from the "About" section doctor list.

**Parameters:**
- `html` (str): HTML content of hospital page
- `hospital_url` (str): Hospital URL

**Returns:** (List[dict]) List of dicts with keys: name, profile_url, hospital_url

---

## Enrichers

### `ProfileEnricher` (`scrapers/marham/enrichers/profile_enricher.py`)

Enriches doctor profiles with detailed information.

#### `parse_doctor_profile(html: str) -> dict`

Parse doctor profile page to extract comprehensive information.

**Parameters:**
- `html` (str): HTML content of doctor profile page

**Returns:** (dict) Dictionary with enriched doctor data including:
- specialties, qualifications, experience, work_history
- services, diseases, symptoms, interests
- professional_statement, patients_treated, reviews_count
- patient_satisfaction_score, phone, consultation_types
- practices (list of hospital/private practice info)

---

## Collectors

### `CityCollector` (`scrapers/marham/collectors/city_collector.py`)

Collects all cities from the Marham hospitals listing page using HTTP requests.

#### `collect_cities() -> List[Dict[str, str]]`

Extract all cities from the hospitals page.

**Returns:** (List[Dict[str, str]]) List of dictionaries with keys: name, url

**Note:** Uses simple HTTP requests (no browser needed). Parses both "Top Cities" and "Other Cities" sections.

---

### `DoctorCollector` (`scrapers/marham/collectors/doctor_collector.py`)

Collects doctor cards from hospital pages, handling dynamic loading.

#### `collect_doctor_cards_from_hospital(scraper: BaseScraper, hospital_url: str) -> List[BeautifulSoup]`

Load hospital page and collect all doctor cards, handling "Load More" buttons.

**Parameters:**
- `scraper` (BaseScraper): BaseScraper instance with active page
- `hospital_url` (str): URL of hospital page

**Returns:** (List[BeautifulSoup]) List of BeautifulSoup Tag objects representing doctor cards

---

## Handlers

### `HospitalPracticeHandler` (`scrapers/marham/handlers/hospital_practice_handler.py`)

Manages hospital practice and doctor-hospital relationships.

#### `upsert_hospital_practice(practice: dict, doctor: DoctorModel) -> None`

Ensure hospital exists and record doctor's practice info for that hospital.

**Parameters:**
- `practice` (dict): Dictionary with hospital practice information
- `doctor` (DoctorModel): DoctorModel instance

**Returns:** None

---

## Mergers

### `DataMerger` (`scrapers/marham/mergers/data_merger.py`)

Handles merging of existing and new records.

#### `merge_doctor_records(existing: dict, new_model: DoctorModel) -> Optional[dict]`

Merge existing doctor document with data from new_model.

**Parameters:**
- `existing` (dict): Existing doctor document from database
- `new_model` (DoctorModel): New DoctorModel instance to merge

**Returns:** (Optional[dict]) Dictionary of fields to update, or None if no changes needed

---

## Utilities

### URL Parser (`scrapers/utils/url_parser.py`)

#### `parse_hospital_url(url: str) -> Dict[str, Optional[str]]`

Extract city, name, and area from hospital URL.

**Parameters:**
- `url` (str): Hospital URL (format: marham.pk/hospitals/(city)/(name)/(area))

**Returns:** (Dict[str, Optional[str]]) Dictionary with keys: city, name, area

#### `is_hospital_url(url: str) -> bool`

Check if URL is a hospital URL.

**Parameters:**
- `url` (str): URL to check

**Returns:** (bool) True if hospital URL

#### `is_doctor_url(url: str) -> bool`

Check if URL is a doctor profile URL.

**Parameters:**
- `url` (str): URL to check

**Returns:** (bool) True if doctor URL

#### `is_video_consultation_url(url: str) -> bool`

Check if URL is for video consultation.

**Parameters:**
- `url` (str): URL to check

**Returns:** (bool) True if video consultation URL

---

### Parser Helpers (`scrapers/utils/parser_helpers.py`)

#### `clean_text(text: Optional[str]) -> Optional[str]`

Clean and normalize text string.

**Parameters:**
- `text` (Optional[str]): Text to clean

**Returns:** (Optional[str]) Cleaned text or None

#### `extract_number(text: Optional[str]) -> Optional[float]`

Extract numeric value from text.

**Parameters:**
- `text` (Optional[str]): Text containing number

**Returns:** (Optional[float]) Extracted number or None

#### `normalize_fee(text: Optional[str]) -> Optional[int]`

Normalize fee text to integer value.

**Parameters:**
- `text` (Optional[str]): Fee text (e.g., "PKR 1,500")

**Returns:** (Optional[int]) Fee as integer or None

#### `safe_get(source: Any, getter: Callable[[Any], Any], default: Any = None) -> Any`

Safely get value using a getter function with default fallback.

**Parameters:**
- `source` (Any): Source object
- `getter` (Callable): Function to extract value
- `default` (Any): Default value if extraction fails

**Returns:** (Any) Extracted value or default

---

## Models

### `DoctorModel` (`scrapers/models/doctor_model.py`)

Pydantic model for doctor data validation.

**Fields:**
- `name` (str): Doctor name
- `profile_url` (str): Doctor profile URL
- `specialty` (List[str]): List of specialties
- `platform` (str): Source platform ('marham', 'oladoc')
- `qualifications` (Optional[List[dict]]): List of qualification dicts
- `experience_years` (Optional[int]): Years of experience
- `work_history` (Optional[List[dict]]): Employment history
- `services` (Optional[List[str]]): List of services
- `diseases` (Optional[List[str]]): List of diseases treated
- `symptoms` (Optional[List[str]]): List of symptoms treated
- `interests` (Optional[List[str]]): List of doctor interests/specializations
- `hospitals` (Optional[List[dict]]): List of hospital affiliations (bidirectional relationship)
- `private_practice` (Optional[dict]): Private practice information
- `professional_statement` (Optional[str]): Professional bio
- `patients_treated` (Optional[int]): Number of patients treated
- `reviews_count` (Optional[int]): Number of reviews
- `patient_satisfaction_score` (Optional[float]): Satisfaction score
- `phone` (Optional[str]): Contact phone number
- `consultation_types` (Optional[List[str]]): Types of consultations
- `scrape_status` (Optional[str]): Scraping workflow status

---

### `HospitalModel` (`scrapers/models/hospital_model.py`)

Pydantic model for hospital data validation.

**Fields:**
- `name` (str): Hospital name
- `url` (str): Hospital URL
- `platform` (str): Source platform
- `city` (Optional[str]): City location
- `area` (Optional[str]): Area/neighborhood
- `address` (Optional[str]): Full address
- `location` (Optional[dict]): Dictionary with 'lat' and 'lng' keys
- `specialties` (Optional[List[str]]): List of specialties
- `founded_year` (Optional[int]): Year hospital was founded
- `achievements` (Optional[List[str]]): List of achievements
- `clinical_departments` (Optional[List[str]]): List of departments
- `specialized_procedures` (Optional[dict]): Dictionary of procedures by category
- `facilities` (Optional[List[str]]): List of facilities
- `clinical_support_services` (Optional[List[str]]): Support services
- `fees_range` (Optional[str]): Fee range description
- `contact_number` (Optional[str]): Contact phone number
- `doctors` (Optional[List[dict]]): List of doctors at hospital
- `scrape_status` (Optional[str]): Scraping workflow status

---

## Scripts

### `run_scraper.py`

Main entry point for running scrapers.

**Command-line arguments:**
- `--site` (required): Site to scrape ('marham', 'oladoc', 'all')
- `--headless`: Run browser in headless mode (default)
- `--no-headless`: Run browser with visible UI
- `--limit` (int): Limit number of profiles per site
- `--disable-js`: Disable JavaScript for faster scraping
- `--test-db`: Use test database instead of production
- `--threads` (int): Number of worker threads (default: 1)
- `--step` (int): Run only specific step (1, 2, or 3)

---

### `scripts/analyze_logs.py`

Analyze scraper logs to extract statistics and performance metrics.

**Command-line arguments:**
- `--log-file` (str): Path to log file (default: logs/dr_doctor_scraper.log)
- `--limit` (int): Filter runs by limit value

---

### `scripts/validate_data.py`

Validate scraped data and generate statistics.

**Command-line arguments:**
- `--test-db`: Validate test database
- `--export-file` (str): Validate exported JSON file

---

### `scripts/export_and_clear_db.py`

Export database to JSON and optionally clear it.

**Command-line arguments:**
- `--clear`: Clear database after export

---

### `scripts/log_diagnostics.py`

Detailed log diagnostics for the most recent scraper run.

**Command-line arguments:**
- `--log-file` (str): Path to log file (default: logs/dr_doctor_scraper.log)

---

## Notes

- All functions use type hints for better IDE support and documentation
- Most functions include comprehensive docstrings
- Error handling is implemented throughout with proper logging
- Thread-safe operations are used in multi-threaded components
- MongoDB operations are atomic and handle duplicates via unique indexes

