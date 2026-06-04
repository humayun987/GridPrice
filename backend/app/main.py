import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.routers import auth, admin
from app.core.scheduler import create_scheduler
from app.services.scraper import scrape_today_mcp
from app.services.weather import fetch_tomorrow_weather
from app.routers import forecasts
from app.routers.exports import router as exports_router

settings = get_settings()

# Create scheduler instance
scheduler = create_scheduler()

app = FastAPI(
    title="tatva.gridprice API",
    description="Electricity market price forecasting platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(forecasts.router)
app.include_router(exports_router)

@app.on_event("startup")
async def startup_event():
    """Starts the scheduler when FastAPI starts."""
    scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Stops the scheduler when FastAPI shuts down."""
    scheduler.shutdown()


@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.APP_ENV}


@app.get("/")
async def root():
    return {"message": "tatva.gridprice API is running"}


@app.post("/test/scrape-mcp")
async def test_scrape_mcp(db: AsyncSession = Depends(get_db)):
    """Manually trigger MCP scraper — for testing only."""
    result = await scrape_today_mcp(db)
    return result


@app.post("/test/fetch-weather")
async def test_fetch_weather(db: AsyncSession = Depends(get_db)):
    """Manually trigger weather fetch — for testing only."""
    result = await fetch_tomorrow_weather(db)
    return result


# @app.post("/test/run-pipeline")
# async def test_run_pipeline(db: AsyncSession = Depends(get_db)):
#     """Manually trigger feature builder + ML pipeline — for testing only."""
#     from app.services.feature_builder import build_features_and_predict
#     result = await build_features_and_predict(db)
#     return result

@app.post("/test/scrape-all-markets")
async def test_scrape_all_markets(db: AsyncSession = Depends(get_db)):
    """Scrape DAM, GDAM, RTM for Telangana — for testing only."""
    from app.services.scraper import scrape_today_mcp
    results = []
    for market in ["GDAM", "DAM", "RTM"]:
        result = await scrape_today_mcp(db, market=market, state="Telangana")
        results.append({"market": market, **result})
    return results


@app.post("/test/run-pipeline")
async def test_run_pipeline(db: AsyncSession = Depends(get_db)):
    """Manually trigger feature builder + ML pipeline — for testing only."""
    from app.services.feature_builder import build_features_and_predict
    result = await build_features_and_predict(db)
    return result