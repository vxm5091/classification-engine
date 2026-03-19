# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### AG Grid & Sortable Transactions Table
- **AG Grid integration** — Replaced manual HTML table with AG Grid Community v35 (`ag-grid-react`, `ag-grid-community`) for sortable columns, resizable columns, and better data handling (`frontend/src/pages/TransactionsPage.jsx`)
- **Server-side sorting** — Default sort is confidence ascending (Low → Medium → High → null) using SQL CASE expressions. Clicking column headers triggers server-side re-sort (`backend/routers/transactions.py`)
- **Row detail panel** — Click any row to expand a detail card below the grid showing reasoning, transaction ID, version, source file, location, and review history

### Batch Filtering by Source File
- **Source files endpoint** — `GET /transactions/source-files` returns distinct source filenames for the batch dropdown (`backend/routers/transactions.py`)
- **Source file filter** — Backend `source_file` query param + frontend "Batch" dropdown to isolate transactions by upload batch (`backend/routers/transactions.py`, `frontend/src/pages/TransactionsPage.jsx`)
- **Vendor search filter** — Backend now handles `vendor_search` param for fuzzy vendor name matching (`backend/routers/transactions.py`)

### Pre-classified CSV Upload Support
- **GL code column detection** — Upload endpoint auto-detects "GL"/"Assigned" column headers in CSVs. When present, transactions are ingested with `confidence="High"`, `method="Pre-classified"`, `review_status="Approved"` (`backend/routers/classify.py`)

### Classification Pipeline Fixes
- **Batched LLM calls** — Vendor resolution (40/batch) and GL classification (30/batch) now process in smaller chunks to prevent JSON truncation/parse errors (`backend/services/classification.py`, `backend/services/vendor_resolution.py`)
- **Increased max_tokens** — LLM calls use 8192 max_tokens (up from 4096) for both vendor resolution and GL classification (`backend/services/llm_classifier.py`, `backend/services/vendor_resolution.py`)
- **Failed transactions marked in DB** — When LLM classification fails or returns null, transactions are now properly marked with `confidence="Low"`, `review_status="Flagged"`, and a failure reason, so they appear correctly in stats and table (`backend/services/classification.py`)

### CSV Drag-and-Drop Upload
- **Backend upload endpoint** — `POST /upload-csv` ingests CSV files, creates `UPL-{nnn}` transactions without classifying (`backend/routers/classify.py`)
- **Upload response schema** — Added `UploadResponse` Pydantic model (`backend/schemas.py`)
- **Frontend API client** — Added `uploadCSV()` function with multipart form data (`frontend/src/api/client.js`)
- **Drag-and-drop on Transactions page** — Full-page drop zone with blue overlay indicator, staged file card with 3 color-coded states (amber=staged, blue=uploaded, green=classified), 2-step flow: "Process Transactions" uploads CSV → "Classify Transactions" runs classification pipeline, cancel/dismiss support (`frontend/src/pages/TransactionsPage.jsx`)

### Bug Fixes
- **GL Reference page** — Fixed API client calling `/gl-codes/hierarchy` instead of `/gl-codes` (hierarchy is the default response)
- **GL Code filter** — Fixed Transactions page GL code dropdown to show level 3 codes instead of hierarchy objects
- **Transaction actions** — Fixed approve/reclassify/flag/convert-to-rule to pass `transaction_id` (string) instead of DB primary key `id`
- **Vite config** — Removed hardcoded port, use `PORT` env var for flexible port assignment; local dev proxy targets port 8002
- **File upload dependency** — Added `python-multipart` to requirements.txt, required by FastAPI for `UploadFile` support (`backend/requirements.txt`)
- **Anthropic SDK compatibility** — Upgraded `anthropic` from pinned `0.39.0` to `>=0.42.0` to fix `proxies` kwarg incompatibility with `httpx>=0.28` (`backend/requirements.txt`)

### Infrastructure Changes
- **Seed script** — Removed CSV ingestion from `seed.py`; transactions are now uploaded exclusively via the UI drag-and-drop feature. Reference data (GL codes, vendors, services, rules) still seeded (`backend/seed.py`)

### Phase 1: Foundation
- **Docker Compose** — PostgreSQL 16, FastAPI backend, React frontend with health checks and volume mounts (`docker-compose.yml`)
- **Database schema** — SQLAlchemy ORM models for Users, GL Codes, Vendors, Vendor Services, Description-Vendor Map (cache), Classification Rules, Transactions (versioned) (`backend/models.py`)
- **Database connection** — SQLAlchemy engine, session factory, dependency injection (`backend/database.py`)
- **Pydantic schemas** — Request/response models for all API endpoints (`backend/schemas.py`)
- **Seed script** — Idempotent seeding of GL codes (39), vendors (107), vendor services (26), classification rules (107), plus CSV ingestion for classified.csv and classify.csv (`backend/seed.py`)
- **Data files** — Copied classified.csv, classify.csv, gl_code_dictionary.csv to `data/` directory

### Phase 2: Classification Engine
- **Non-expense detection** — Keyword-based detection for AUTOPAY/payment transactions, excluded from classification pipeline (`backend/services/classification.py`)
- **Vendor cache** — Description-vendor map CRUD with pattern normalization (uppercase, strip, collapse spaces) (`backend/services/vendor_cache.py`)
- **Vendor resolution** — Cache-first architecture with batched LLM fallback for unseen descriptions. Auto-creates new vendors/services. Single API call for all uncached patterns (`backend/services/vendor_resolution.py`)
- **Rule engine** — Deterministic matching by vendor, service, amount range, and time-of-month. Handles single match (High), consistent multi-match (High), and conflicting multi-match (Low/Flagged) (`backend/services/rule_engine.py`)
- **LLM classifier** — Batched GL code inference for rule-unmatched transactions with historical comparables and GL hierarchy context (`backend/services/llm_classifier.py`)
- **Pipeline orchestrator** — Ties together non-expense → vendor resolution → rule engine → LLM classifier (`backend/services/classification.py`)

### Phase 3: API Layer
- **FastAPI app** — CORS-enabled, all routers under `/api` prefix, startup table creation (`backend/main.py`)
- **Transaction endpoints** — Paginated list with filters (confidence, GL code, review status, vendor, date range), detail with version history, approve/reclassify/flag actions (versioned), convert-to-rule (`backend/routers/transactions.py`)
- **Rules endpoints** — CRUD with match count statistics, deactivate support (`backend/routers/rules.py`)
- **Vendor endpoints** — CRUD with search, service/transaction counts, confirm workflow, nested service management (`backend/routers/vendors.py`)
- **GL codes endpoint** — Hierarchical tree view or flat list by level (`backend/routers/gl_codes.py`)
- **Classify endpoint** — Triggers classification pipeline on unclassified transactions (`backend/routers/classify.py`)
- **Stats endpoint** — Aggregate counts by review status, confidence, method, GL code (`backend/routers/stats.py`)

### Phase 4: Frontend
- **React app scaffold** — Vite + TailwindCSS v4 + TanStack Query v5 + React Router v6 (`frontend/`)
- **Layout** — Sidebar navigation with active states, header bar (`frontend/src/components/layout/`)
- **API client** — Axios instance with all API functions (`frontend/src/api/client.js`)
- **React Query hooks** — Custom hooks for transactions, rules, vendors with mutations (`frontend/src/hooks/`)
- **Shared components** — ConfidenceBadge, ReviewBadge, StatsBar (`frontend/src/components/shared/`)
- **Transactions page** — Stats bar, 6 filters, sortable table, expandable rows with reasoning, approve/reclassify/flag/convert-to-rule actions, pagination, muted non-expense rows (`frontend/src/pages/TransactionsPage.jsx`)
- **Reclassify modal** — GL hierarchy selector, current assignment, notes field (`frontend/src/components/transactions/ReclassifyModal.jsx`)
- **Convert to Rule modal** — Prepopulated vendor/service/amount/GL fields (`frontend/src/components/transactions/ConvertToRuleModal.jsx`)
- **Rules page** — Table with create/edit modal, deactivate action (`frontend/src/pages/RulesPage.jsx`)
- **Vendors page** — Table with search, pending confirmation banner, expandable services, confirm button (`frontend/src/pages/VendorsPage.jsx`)
- **GL Reference page** — Hierarchical tree view with expand/collapse and search (`frontend/src/pages/GLReferencePage.jsx`)
                                                                                                                   