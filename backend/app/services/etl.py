"""
HDB Resale ETL Pipeline
-----------------------
Step 1 - Extract:   Paginated fetch from data.gov.sg public API.
                    Resource ID: d_8b84c4ee58e3cfc0ece0d773c8ca6abc
                    Filters to last 5 years to keep DB size manageable.
Step 2 - Transform: Parse field types, derive price_per_sqm, drop invalid rows.
Step 3 - Load:      Bulk insert into SQLite (skips if DB already populated).

Falls back to a small deterministic seed dataset when the API is unreachable,
so the app still runs in offline/CI environments. Seed data is clearly labelled
in the log so it cannot be silently mistaken for real transactions.
"""

import logging
from typing import Optional

import httpx
from sqlalchemy import text

from app.db.database import AsyncSessionLocal
from app.models.models import Transaction

logger = logging.getLogger(__name__)

_API_BASE = "https://data.gov.sg/api/action/datastore_search"
_RESOURCE_ID = "d_8b84c4ee58e3cfc0ece0d773c8ca6abc"
_PAGE_SIZE = 1000
_START_MONTH = "2020-01"


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

async def fetch_from_api() -> Optional[list[dict]]:
    """
    Pull all HDB resale records from data.gov.sg from _START_MONTH onwards.
    Returns list of raw record dicts, or None if the API is unreachable.
    """
    all_records: list[dict] = []
    offset = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            try:
                resp = await client.get(
                    _API_BASE,
                    params={
                        "resource_id": _RESOURCE_ID,
                        "limit": _PAGE_SIZE,
                        "offset": offset,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("data.gov.sg API error at offset %d: %s", offset, exc)
                return None

            body = resp.json()
            if not body.get("success"):
                logger.warning("data.gov.sg returned success=false at offset %d", offset)
                return None

            result = body["result"]
            records = result.get("records", [])
            total = result.get("total", 0)

            # Filter to months >= _START_MONTH client-side (API has no range filter)
            recent = [r for r in records if r.get("month", "") >= _START_MONTH]
            all_records.extend(recent)

            offset += _PAGE_SIZE
            if offset >= total:
                break

            # If the batch had no recent records and we're past the start threshold,
            # the data is sorted oldest-first so we can stop early
            if records and records[-1].get("month", "") < _START_MONTH:
                logger.info("Reached records older than %s, stopping pagination", _START_MONTH)
                break

    logger.info("API fetch complete: %d records from %s onwards", len(all_records), _START_MONTH)
    return all_records


# ---------------------------------------------------------------------------
# Fallback seed (offline / CI use)
# ---------------------------------------------------------------------------

def _seed_records(n: int = 3000) -> list[dict]:
    """Deterministic synthetic data when API is unreachable."""
    import random

    TOWNS = [
        "ANG MO KIO", "BEDOK", "BISHAN", "BUKIT BATOK", "BUKIT MERAH",
        "BUKIT PANJANG", "CENTRAL AREA", "CHOA CHU KANG", "CLEMENTI",
        "GEYLANG", "HOUGANG", "JURONG EAST", "JURONG WEST",
        "KALLANG/WHAMPOA", "MARINE PARADE", "PASIR RIS", "PUNGGOL",
        "QUEENSTOWN", "SEMBAWANG", "SENGKANG", "SERANGOON", "TAMPINES",
        "TOA PAYOH", "WOODLANDS", "YISHUN",
    ]
    FLAT_TYPES = ["2 ROOM", "3 ROOM", "4 ROOM", "5 ROOM", "EXECUTIVE"]
    MODELS = ["Improved", "New Generation", "Model A", "Standard", "Premium Apartment"]
    STOREYS = [
        "01 TO 03", "04 TO 06", "07 TO 09", "10 TO 12",
        "13 TO 15", "16 TO 18", "19 TO 21", "22 TO 24",
    ]
    BASE = {"2 ROOM": 260000, "3 ROOM": 380000, "4 ROOM": 540000,
            "5 ROOM": 680000, "EXECUTIVE": 820000}
    AREA = {"2 ROOM": (48, 55), "3 ROOM": (65, 80), "4 ROOM": (90, 105),
            "5 ROOM": (110, 130), "EXECUTIVE": (130, 160)}
    TOWN_M = {
        "CENTRAL AREA": 1.55, "QUEENSTOWN": 1.45, "BISHAN": 1.40,
        "MARINE PARADE": 1.35, "TOA PAYOH": 1.30, "KALLANG/WHAMPOA": 1.28,
        "BUKIT MERAH": 1.25, "GEYLANG": 1.20, "CLEMENTI": 1.22,
        "ANG MO KIO": 1.18, "SERANGOON": 1.18, "TAMPINES": 1.15,
        "BEDOK": 1.12, "HOUGANG": 1.08, "PASIR RIS": 1.05,
        "JURONG EAST": 1.05, "SENGKANG": 1.02, "PUNGGOL": 1.00,
        "BUKIT BATOK": 1.00, "BUKIT PANJANG": 0.97, "JURONG WEST": 0.98,
        "CHOA CHU KANG": 0.95, "YISHUN": 0.95, "WOODLANDS": 0.93,
        "SEMBAWANG": 0.92,
    }
    STOREY_M = {
        "01 TO 03": 0.92, "04 TO 06": 0.95, "07 TO 09": 0.98,
        "10 TO 12": 1.01, "13 TO 15": 1.04, "16 TO 18": 1.07,
        "19 TO 21": 1.10, "22 TO 24": 1.13,
    }

    rng = random.Random(42)
    months = []
    y, mo = 2020, 1
    while (y, mo) <= (2024, 12):
        months.append(f"{y:04d}-{mo:02d}")
        mo = mo % 12 + 1
        if mo == 1:
            y += 1

    records = []
    for _ in range(n):
        town = rng.choice(TOWNS)
        ft = rng.choice(FLAT_TYPES)
        storey = rng.choice(STOREYS)
        month = rng.choice(months)
        lo, hi = AREA[ft]
        area = round(rng.uniform(lo, hi), 1)
        years_elapsed = (int(month[:4]) - 2020) + (int(month[5:]) - 1) / 12
        price = (
            BASE[ft]
            * TOWN_M.get(town, 1.0)
            * STOREY_M.get(storey, 1.0)
            * (1.04 ** years_elapsed)
            * rng.uniform(0.93, 1.07)
        )
        price = round(price / 1000) * 1000
        lease_year = rng.randint(1970, 2010)
        records.append({
            "month": month,
            "town": town,
            "flat_type": ft,
            "block": str(rng.randint(1, 999)),
            "street_name": f"{town} ST {rng.randint(1, 30)}",
            "storey_range": storey,
            "floor_area_sqm": str(area),
            "flat_model": rng.choice(MODELS),
            "lease_commence_date": str(lease_year),
            "remaining_lease": f"{99 - (2024 - lease_year)} years",
            "resale_price": str(int(price)),
        })
    return records


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------

def _transform(raw: list[dict]) -> list[dict]:
    clean = []
    for r in raw:
        try:
            price = float(r["resale_price"])
            area = float(r["floor_area_sqm"])
            if price <= 0 or area <= 0:
                continue
            clean.append({
                "month": str(r.get("month", "")).strip(),
                "town": str(r.get("town", "")).strip().upper(),
                "flat_type": str(r.get("flat_type", "")).strip().upper(),
                "block": str(r.get("block", "")).strip(),
                "street_name": str(r.get("street_name", "")).strip(),
                "storey_range": str(r.get("storey_range", "")).strip(),
                "floor_area_sqm": area,
                "flat_model": str(r.get("flat_model", "")).strip(),
                "lease_commence_date": int(r["lease_commence_date"]) if r.get("lease_commence_date") else None,
                "remaining_lease": str(r.get("remaining_lease", "")).strip(),
                "resale_price": price,
                "price_per_sqm": round(price / area, 2),
            })
        except (ValueError, KeyError, TypeError):
            continue
    return clean


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

async def _load(records: list[dict]) -> int:
    async with AsyncSessionLocal() as session:
        objects = [Transaction(**r) for r in records]
        session.add_all(objects)
        await session.commit()
    return len(records)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

async def run_etl_pipeline() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM transactions"))
        count = result.scalar() or 0

    if count > 0:
        logger.info("DB already contains %d transactions -- skipping ETL", count)
        return

    logger.info("Step 1/3 -- Extracting from data.gov.sg API (resource %s)...", _RESOURCE_ID)
    raw = await fetch_from_api()

    if raw is None:
        logger.warning("API unreachable -- falling back to synthetic seed data")
        raw = _seed_records(3000)
        logger.warning("SEED DATA ACTIVE: charts reflect synthetic transactions, not real HDB records")
    else:
        logger.info("API returned %d raw records", len(raw))

    logger.info("Step 2/3 -- Transforming and validating...")
    clean = _transform(raw)
    logger.info("  %d records passed validation (dropped %d)", len(clean), len(raw) - len(clean))

    logger.info("Step 3/3 -- Loading into database...")
    loaded = await _load(clean)
    logger.info("ETL complete -- %d transactions in DB", loaded)
