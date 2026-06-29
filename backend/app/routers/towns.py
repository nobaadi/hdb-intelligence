from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.database import get_db

router = APIRouter()


@router.get("/")
async def list_towns(db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("SELECT DISTINCT town FROM transactions ORDER BY town"))
    return [row[0] for row in r]


@router.get("/flat-types")
async def list_flat_types(db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("SELECT DISTINCT flat_type FROM transactions ORDER BY flat_type"))
    return [row[0] for row in r]
