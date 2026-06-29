import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import engine, Base
from app.routers import transactions, analytics, towns
from app.services.etl import run_etl_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_etl_pipeline()
    logger.info("Startup complete")
    yield


app = FastAPI(
    title="HDB Resale Intelligence API",
    description="ETL pipeline + analytics API for Singapore HDB resale transactions",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(towns.router, prefix="/api/towns", tags=["towns"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hdb-intelligence"}
