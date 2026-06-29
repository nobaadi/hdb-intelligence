from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.database import get_db

router = APIRouter()


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT
            COUNT(*)                          AS total_transactions,
            ROUND(AVG(resale_price), 0)       AS avg_price,
            ROUND(AVG(price_per_sqm), 2)      AS avg_price_per_sqm,
            MIN(month)                        AS data_from,
            MAX(month)                        AS data_to
        FROM transactions
    """))
    row = dict(r.mappings().one())

    top = await db.execute(text("""
        SELECT town, COUNT(*) AS cnt
        FROM transactions
        GROUP BY town ORDER BY cnt DESC LIMIT 1
    """))
    top_row = dict(top.mappings().one())

    return {**row, "busiest_town": top_row["town"], "busiest_town_count": top_row["cnt"]}


@router.get("/trend")
async def get_price_trend(
    flat_type: str = None,
    town: str = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    params: dict = {}
    if flat_type:
        conditions.append("flat_type = :flat_type")
        params["flat_type"] = flat_type.upper()
    if town:
        conditions.append("town = :town")
        params["town"] = town.upper()
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    r = await db.execute(
        text(f"""
            SELECT month,
                   ROUND(AVG(resale_price), 0) AS avg_price,
                   COUNT(*)                    AS volume
            FROM transactions
            {where}
            GROUP BY month
            ORDER BY month
        """),
        params,
    )
    return [dict(row) for row in r.mappings()]


@router.get("/by-town")
async def prices_by_town(flat_type: str = None, db: AsyncSession = Depends(get_db)):
    params: dict = {}
    where = ""
    if flat_type:
        where = "WHERE flat_type = :flat_type"
        params["flat_type"] = flat_type.upper()

    r = await db.execute(
        text(f"""
            SELECT town,
                   ROUND(AVG(resale_price), 0)  AS avg_price,
                   ROUND(AVG(price_per_sqm), 2) AS avg_psm,
                   COUNT(*)                      AS volume
            FROM transactions
            {where}
            GROUP BY town ORDER BY avg_price DESC
        """),
        params,
    )
    return [dict(row) for row in r.mappings()]


@router.get("/by-flat-type")
async def prices_by_flat_type(town: str = None, db: AsyncSession = Depends(get_db)):
    params: dict = {}
    where = ""
    if town:
        where = "WHERE town = :town"
        params["town"] = town.upper()

    r = await db.execute(
        text(f"""
            SELECT flat_type,
                   ROUND(AVG(resale_price), 0) AS avg_price,
                   COUNT(*) AS volume
            FROM transactions
            {where}
            GROUP BY flat_type
            ORDER BY avg_price
        """),
        params,
    )
    return [dict(row) for row in r.mappings()]


@router.get("/storey-premium")
async def storey_premium(db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT storey_range,
               ROUND(AVG(resale_price), 0) AS avg_price,
               COUNT(*) AS volume
        FROM transactions
        GROUP BY storey_range
        ORDER BY avg_price
    """))
    return [dict(row) for row in r.mappings()]


@router.get("/yoy")
async def year_on_year(db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT SUBSTR(month, 1, 4) AS year,
               ROUND(AVG(resale_price), 0) AS avg_price,
               COUNT(*) AS volume
        FROM transactions
        GROUP BY year ORDER BY year
    """))
    rows = [dict(row) for row in r.mappings()]
    for i in range(1, len(rows)):
        prev = rows[i - 1]["avg_price"]
        curr = rows[i]["avg_price"]
        rows[i]["yoy_change_pct"] = round((curr - prev) / prev * 100, 2) if prev else None
    if rows:
        rows[0]["yoy_change_pct"] = None
    return rows
