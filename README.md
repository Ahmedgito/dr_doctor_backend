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

## Current Phase

**Phase 1: Scraper Refinement & Testing** 🔄

We are currently refining the Marham scraper to capture comprehensive doctor and hospital data, with testing planned at increasing scales (5 → 100 → all Karachi hospitals).

## Development Status

### Completed ✅
- ✅ Marham scraper (hospital-first approach) - Created and tested
- ✅ Modular scraper architecture (parsers, enrichers, collectors, mergers)
- ✅ Oladoc scraper (basic implementation)
- ✅ MongoDB integration with upsert support
- ✅ Data export/import utilities
- ✅ Project structure and file organization
- ✅ Bidirectional doctor-hospital relationships
- ✅ Comprehensive doctor data capture (interests, services, diseases, symptoms)
- ✅ Queue-based dynamic work distribution for all steps
- ✅ Page tracking and retry system

### In Progress 🔄
- 🔄 Testing and validation of bidirectional relationships
- 🔄 Performance optimization

### Planned 📋
- 📋 Testing with 100 hospitals
- 📋 Scaling to all hospitals in Karachi
- 📋 Additional platform scrapers
- 📋 User queries and doctor replies collection
- 📋 Patient reviews and ratings collection
- 📋 Autonomous scraping/crawling system

## Project Roadmap

This project follows a phased development approach to build a comprehensive healthcare data platform with AI-powered chatbot capabilities.

### Phase 1: Scraper Refinement & Testing (Current) 🔄

**Goal**: Build and validate a robust scraper that captures comprehensive doctor and hospital data.

- ✅ Create and test Marham base scraper
- 🔄 Refactor to include comprehensive doctor and hospital data fields
- 📋 Test with 5 hospitals
- 📋 Test with 100 hospitals
- 📋 Scale to all hospitals in Karachi
- 📋 Validate data quality and completeness

**Deliverables**: Production-ready Marham scraper with complete data capture

---

### Phase 2: Data Collection Expansion 📋

**Goal**: Expand data collection to include user interactions and reviews, and make the system autonomous.

- 📋 Refactor codebase to gather complete hospital data across all available fields
- 📋 Collect user queries and doctor replies from platform Q&A sections
- 📋 Collect patient reviews and ratings
- 📋 Implement autonomous scraping/crawling with scheduling and error recovery
- 📋 Add monitoring and alerting for scraper health

**Deliverables**: Autonomous scraping system with comprehensive data collection

---

### Phase 3: Multi-Platform Integration 📋

**Goal**: Integrate data from multiple healthcare platforms and create a unified data model.

- 📋 Complete Oladoc scraper integration
- 📋 Add scrapers for additional platforms (AKU, etc.)
- 📋 Build data merging and deduplication pipeline
- 📋 Create unified data model across all platforms
- 📋 Implement data quality validation and normalization

**Deliverables**: Multi-platform data aggregation system with unified schema

---

### Phase 4: ML & NLP Foundation 📋

**Goal**: Build the AI foundation for intelligent patient assistance.

- 📋 Build Rasa/Reg model for chatbot foundation
- 📋 Train models on collected doctor/hospital data
- 📋 Implement natural language understanding for medical queries
- 📋 Create intent classification and entity extraction
- 📋 Build conversation flow management

**Deliverables**: Functional chatbot with medical domain knowledge

---

### Phase 5: Advanced Features 📋

**Goal**: Add intelligent features for enhanced user experience and data collection.

- 📋 Text-to-speech integration for accessibility
- 📋 Local language detection via user location (Urdu, regional languages)
- 📋 Location-based hospital/clinic finder (20km radius)
- 📋 ML-based intelligent scraper/crawler for data lake
- 📋 Automated data cleaning pipeline
- 📋 Model training and inference pipeline
- 📋 Real-time data enrichment and updates

**Deliverables**: Intelligent features with ML-powered data collection

---

### Phase 6: Frontend Development 📋

**Goal**: Build user and doctor-facing interfaces with advanced medical features.

#### User-Facing Frontend (Patient Portal)
- 📋 Patient registration and profile management
- 📋 Hospital/doctor search and filtering
- 📋 Appointment booking interface
- 📋 Test result scanning and interpretation
- 📋 Chat interface with AI assistant
- 📋 Medical history tracking

#### Doctor-Facing Frontend (Doctor Dashboard)
- 📋 Doctor profile management
- 📋 Patient history and records
- 📋 Evidence-Based Medicine (EBM) references and integration
- 📋 Test results analysis and interpretation tools
- 📋 AI-assisted diagnosis suggestions
- 📋 Prognosis and treatment planning tools
- 📋 Patient communication interface

**Deliverables**: Complete frontend applications for patients and doctors

---

### Phase 7: Integration & Deployment 📋

**Goal**: Integrate all components and deploy to production.

- 📋 End-to-end integration of all components
- 📋 Comprehensive testing (unit, integration, E2E)
- 📋 Performance optimization and scaling
- 📋 Security audit and compliance (HIPAA considerations)
- 📋 Production deployment and monitoring
- 📋 Documentation and user guides
- 📋 Maintenance and support plan

**Deliverables**: Production-ready, fully integrated healthcare platform

---

## Notes

- The scraper uses a hospital-first approach for Marham, collecting hospitals first then doctors within each hospital
- Data is stored in MongoDB with unique indexes on `profile_url` (doctors) and `name+address` (hospitals)
- Export/import tools are available in `scrapers/tools/` for sharing database snapshots
- The roadmap is iterative - phases may overlap and priorities may shift based on learnings and requirements
