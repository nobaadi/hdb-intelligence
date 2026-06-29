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

## Jupyter Notebook

`notebooks/singapore_housing_analysis.ipynb` is a standalone EDA notebook that fetches directly from the data.gov.sg API. No backend or Docker required.

```bash
pip install pandas requests matplotlib seaborn scipy scikit-learn
jupyter notebook notebooks/singapore_housing_analysis.ipynb
```

The notebook covers five analyses:

| Analysis | Method |
|---|---|
| Price trend 2020 to present | Monthly median + Mann-Whitney U test on pre/post Sep 2022 cooling measure |
| Town-level premium | Median price per town, top-5 vs bottom-5 premium ratio |
| Storey premium | Price per sqm by floor band, Pearson correlation (storey vs price) |
| Flat type distribution | Boxplots with IQR, quartile summary |
| OLS price prediction | LinearRegression on floor area + storey + town + flat type; R2, MAE, residual plot |

---

## SQL Analytics

`sql/analytics.sql` contains seven queries demonstrating window functions and CTE chains against the transactions table. Two examples:

**Town ranking -- RANK, DENSE_RANK, PERCENT_RANK, NTILE in one query:**

```sql
WITH town_stats AS (
    SELECT
        town,
        ROUND(AVG(resale_price), 0)  AS avg_price,
        COUNT(*)                      AS volume
    FROM transactions
    GROUP BY town
)
SELECT
    town,
    avg_price,
    RANK()         OVER (ORDER BY avg_price DESC)  AS price_rank,
    DENSE_RANK()   OVER (ORDER BY avg_price DESC)  AS dense_rank,
    ROUND(PERCENT_RANK() OVER (ORDER BY avg_price), 4) AS percentile,
    NTILE(4)       OVER (ORDER BY avg_price DESC)  AS price_quartile
FROM town_stats
ORDER BY avg_price DESC;
```

**Storey premium -- FIRST_VALUE to compute premium vs ground floor:**

```sql
WITH storey_stats AS (
    SELECT
        storey_range,
        ROUND(AVG(resale_price), 0) AS avg_price,
        COUNT(*)                     AS volume
    FROM transactions
    GROUP BY storey_range
)
SELECT
    storey_range,
    avg_price,
    avg_price - FIRST_VALUE(avg_price) OVER (
        ORDER BY avg_price
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS premium_vs_lowest
FROM storey_stats
ORDER BY avg_price;
```

Full query list: (1) MoM price delta with LAG, (2) town ranking with 4 window functions, (3) rolling 3-month average with ROWS BETWEEN, (4) storey premium with FIRST_VALUE, (5) YoY flat type change with CTE + LAG, (6) price quartiles per town with NTILE, (7) overvaluation signal with divergence CTE chain.

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
├── notebooks/
│   └── singapore_housing_analysis.ipynb  # Standalone EDA notebook (no backend needed)
├── sql/
│   └── analytics.sql            # Window function and CTE analytics queries
├── docker-compose.yml
└── README.md
```
