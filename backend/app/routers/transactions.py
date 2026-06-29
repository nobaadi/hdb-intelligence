from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.database import get_db

router = APIRouter()


@router.get("/")
async def list_transactions(
    town: str = None,
    flat_type: str = None,
    min_price: float = None,
    max_price: float = None,
    month_from: str = None,
    month_to: str = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}

    if town:
        conditions.append("town = :town")
        params["town"] = town.upper()
    if flat_type:
        conditions.append("flat_type = :flat_type")
        params["flat_type"] = flat_type.upper()
    if min_price is not None:
        conditions.append("resale_price >= :min_price")
        params["min_price"] = min_price
    if max_price is not None:
        conditions.append("resale_price <= :max_price")
        params["max_price"] = max_price
    if month_from:
        conditions.append("month >= :month_from")
        params["month_from"] = month_from
    if month_to:
        conditions.append("month <= :month_to")
        params["month_to"] = month_to

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    count_r = await db.execute(text(f"SELECT COUNT(*) FROM transactions {where}"), count_params)
    total = count_r.scalar()

    rows_r = await db.execute(
        text(f"""
            SELECT id, month, town, flat_type, block, street_name, storey_range,
                   floor_area_sqm, flat_model, lease_commence_date, remaining_lease,
                   resale_price, price_per_sqm
            FROM transactions {where}
            ORDER BY month DESC, resale_price DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    rows = [dict(row) for row in rows_r.mappings()]
    return {"total": total, "page": page, "page_size": page_size, "data": rows}
