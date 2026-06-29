# HDB Resale Intelligence Platform

A full-stack analytics platform for Singapore public housing resale prices. The ETL pipeline ingests transaction records directly from the data.gov.sg public API, stores them in SQLite, and exposes a FastAPI analytics layer consumed by an interactive Chart.js dashboard.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![SQLite](https://img.shields.io/badge/SQLite-async-003B57?logo=sqlite&logoColor=white)](https://sqlite.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![data.gov.sg](https://img.shields.io/badge/data-data.gov.sg-e01e5a)](https://data.gov.sg)

---

## What It Does

Four dashboard tabs, all driven by live API calls to the backend:

| Tab | What you see |
|-----|-------------|
| **Overview** | KPI cards (total transactions, avg price, avg price/sqm, busiest town), year-on-year price chart, volume by flat type |
| **Price by Town** | Horizontal bar chart of average resale price per town, filterable by flat type |
| **Price Trend** | Monthly average price line + volume bar chart, filterable by town and flat type |
| **Transaction Explorer** | Paginated transaction table with filters: town, flat type, month range, price range |

---

## Data Source

**HDB Resale Flat Prices** from data.gov.sg.

- Resource ID: `d_8b84c4ee58e3cfc0ece0d773c8ca6abc`
- API endpoint: `https://data.gov.sg/api/action/datastore_search`
- Coverage: all HDB resale transactions from 1990 to present
- The ETL filters to records from 2020 onwards to keep the database at a manageable size

The ETL pipeline fetches paginated records (1000 per request) and filters client-side to the configured start month. If the API is unreachable at startup, it falls back to a small deterministic synthetic dataset (3000 records) so the app remains runnable offline. The dashboard header badge shows whether live or synthetic data is active.

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/nobaadi/hdb-intelligence
cd hdb-intelligence
docker compose up --build
```

Open `frontend/index.html` in your browser. The backend runs at `http://localhost:8002`.

The ETL runs automatically on first startup. First launch pulls data from data.gov.sg and takes 30-60 seconds depending on API response time. Subsequent launches skip the ETL since data is already in the SQLite volume.

### Manual

**Backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

**Frontend**

Open `frontend/index.html` directly in a browser. No build step required.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/summary` | KPI summary: total count, avg price, avg psm, date range, busiest town |
| GET | `/api/analytics/trend` | Monthly avg price and volume; params: `town`, `flat_type` |
| GET | `/api/analytics/by-town` | Avg price per town; param: `flat_type` |
| GET | `/api/analytics/by-flat-type` | Avg price by flat type; param: `town` |
| GET | `/api/analytics/storey-premium` | Avg price per storey band |
| GET | `/api/analytics/yoy` | Year-on-year avg price and YoY change % |
| GET | `/api/transactions/` | Paginated transaction list; params: `town`, `flat_type`, `month_from`, `month_to`, `min_price`, `max_price`, `page`, `page_size` |
| GET | `/api/towns/` | Distinct town list |
| GET | `/api/towns/flat-types` | Distinct flat type list |
| GET | `/health` | Health check |

Interactive docs at `http://localhost:8002/docs` (Swagger UI).

---

## Architecture Decisions

**Why SQLite instead of PostgreSQL?** The full 2020-present dataset is around 60k records and fits comfortably in a single SQLite file (under 50 MB). SQLite with aiosqlite and the async SQLAlchemy engine gives sub-10ms query times on all analytics endpoints. Swapping to PostgreSQL requires only changing `DATABASE_URL` -- the SQLAlchemy layer abstracts everything else.

**Why paginate the data.gov.sg API?** The `datastore_search` endpoint returns at most 32767 records per call. The full HDB dataset exceeds 200k records, so the ETL paginates with 1000 records per request and filters to recent years client-side. The `datastore_search_sql` endpoint would allow server-side date filtering, but is less stable across API versions.

**Why parameterized queries?** All router endpoints use SQLAlchemy's named-parameter binding (`:town`, `:flat_type`, etc.) rather than f-string interpolation. String interpolation in SQL query construction is a SQL injection vulnerability regardless of whether the input looks safe.

**Why a single HTML frontend?** No build pipeline, no Node.js dependency, no framework churn. Chart.js from CDN covers all visualization needs. The frontend is a single file that can be opened directly in a browser or served from any static host.

---

## SQL Analytics

`sql/analytics.sql` contains seven production-quality queries demonstrating advanced SQL patterns against the transactions table:

1. Month-over-month price delta with LAG window function
2. Town ranking with RANK, DENSE_RANK, PERCENT_RANK, NTILE(4)
3. Rolling 3-month average price with ROWS BETWEEN frame
4. Storey premium analysis with SUM() OVER and FIRST_VALUE
5. Year-on-year change by flat type (CTE chain + LAG)
6. Price distribution quartiles per town with NTILE
7. Town divergence from long-run average (CTE chain with overvaluation signal)

---

## Project Structure

```
hdb-intelligence/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, lifespan ETL trigger
│   │   ├── db/database.py       # Async SQLAlchemy engine, Base, get_db
│   │   ├── models/models.py     # Transaction ORM model with composite indexes
│   │   ├── routers/
│   │   │   ├── analytics.py     # /api/analytics/* endpoints
│   │   │   ├── transactions.py  # /api/transactions/ with pagination and filters
│   │   │   └── towns.py         # /api/towns/ reference data
│   │   └── services/etl.py      # data.gov.sg fetch, transform, load, fallback seed
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── index.html               # Single-page dashboard (Chart.js, vanilla JS)
├── sql/
│   └── analytics.sql            # Window function and CTE analytics queries
├── docker-compose.yml
└── README.md
```
