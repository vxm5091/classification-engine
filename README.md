# Classification Engine

A GL code classification tool for categorizing financial transactions. Uses a deterministic rule engine with LLM-powered rule suggestions, vendor resolution, and conflict advisory.

## Architecture

- **Frontend** — React + Vite + TailwindCSS + AG Grid (port 5173)
- **Backend** — FastAPI + SQLAlchemy (port 8002)
- **Database** — PostgreSQL 16 (port 5432)
- **LLM** — Anthropic Claude API for vendor resolution and rule suggestions

## Getting Started

### Prerequisites

- Docker and Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone and configure

```bash
git clone <repo-url> && cd classification-engine
cp .env.example .env
```

Edit `.env` and set your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2. Start the stack

```bash
docker compose up -d --build
```

This starts three containers:

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:5173 | React UI |
| Backend | http://localhost:8002 | FastAPI API |
| Database | localhost:5432 | PostgreSQL |

The backend automatically creates database tables on startup.

### 3. Seed reference data

Run the seed script to populate GL codes, initial vendors, services, and classification rules:

```bash
docker compose exec backend python -m backend.seed
```

### 4. Open the app

Navigate to http://localhost:5173. You can:

1. **Drag & drop a CSV** onto the transactions page to upload
2. **Process** to ingest transactions
3. **Classify** to run the rule engine + vendor resolution
4. **Suggest Rules** for any unclassified transactions (triggers LLM)
5. **Approve/edit** suggested rules, then **Re-classify**

### CSV Format

The upload accepts CSVs with these columns (header names are flexible):

| Column | Required | Examples |
|--------|----------|---------|
| Date | Yes | `01/15/2025`, `1/15/25`, `2025-01-15` |
| Description | Yes | `AMAZON.COM AMZN.COM/BILL WA` |
| Amount | Yes | `150.38`, `$1,200.00`, `($50.00)` |
| GL Code / Assigned GL Code | No | `6200` (pre-classifies the transaction) |

## Useful Commands

```bash
# Rebuild after code changes
docker compose up -d --build

# View backend logs
docker compose logs backend --tail 50

# Open a psql shell
docker compose exec db psql -U gluser -d gl_classifier

# Stop everything
docker compose down

# Stop and remove database volume (full reset)
docker compose down -v
```

## Project Structure

```
classification-engine/
├── backend/
│   ├── main.py                  # FastAPI app + startup
│   ├── models.py                # SQLAlchemy models
│   ├── schemas.py               # Pydantic request/response schemas
│   ├── seed.py                  # Reference data seeder
│   ├── routers/
│   │   ├── classify.py          # Upload, classify, suggest-rules, reclassify
│   │   ├── transactions.py      # Transaction CRUD + review actions
│   │   └── rules.py             # Classification rules CRUD
│   └── services/
│       ├── classification.py    # Classification pipeline orchestration
│       ├── rule_engine.py       # Deterministic rule matching + specificity
│       ├── vendor_resolution.py # Cache-first vendor resolution with LLM fallback
│       ├── llm_rule_suggester.py    # LLM-based rule suggestion engine
│       └── llm_conflict_advisor.py  # LLM advisory for rule conflicts
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── TransactionsPage.jsx  # Main transactions table + detail card
│       │   └── RulesPage.jsx         # Classification rules management
│       ├── components/
│       │   └── transactions/
│       │       ├── RuleSuggestionsPanel.jsx
│       │       ├── ConvertToRuleModal.jsx
│       │       └── ReclassifyModal.jsx
│       ├── api/client.js         # Axios API client
│       └── hooks/useTransactions.js  # React Query hooks
├── data/                         # CSV files and snapshots
├── plans/                        # Implementation plans and changelog
├── docker-compose.yml
└── .env.example
```
