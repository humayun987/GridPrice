import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.routers import auth, admin
from app.core.scheduler import create_scheduler
from app.services.scraper import scrape_today_mcp
from app.core.scheduler import run_mcp_scraper, run_pipeline
from app.services.weather import fetch_tomorrow_weather
from app.routers import forecasts
from app.routers.exports import router as exports_router
from app.core.redis import cache_delete_pattern
from app.core.deps import require_admin
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter

settings = get_settings()

scheduler = create_scheduler()


# ─── Security Headers Middleware ──────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="tatva.gridprice API",
    description="Electricity market price forecasting platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://grid-price-khaki.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(forecasts.router)
app.include_router(exports_router)


# ─── Lifecycle ────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()


# ─── Core endpoints ───────────────────────────────────────────────────────────

@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok", "environment": settings.APP_ENV}


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": "tatva.gridprice API is running"}


# ─── Test endpoints (admin only) ──────────────────────────────────────────────

@app.post("/test/scrape-mcp")
async def test_scrape_mcp(
    market: str = Query("GDAM"),
    state: str = Query("Telangana"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Manually trigger MCP scraper for a single market — for testing only."""
    result = await scrape_today_mcp(db, market=market, state=state)
    return result


@app.post("/test/scrape-all-markets")
async def test_scrape_all_markets(
    state: str = Query("Telangana"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Scrape DAM, GDAM, RTM for a given state — for testing only."""
    results = []
    for market in ["GDAM", "DAM", "RTM"]:
        result = await scrape_today_mcp(db, market=market, state=state)
        results.append({"market": market, **result})

    for market in ["GDAM", "DAM", "RTM"]:
        await cache_delete_pattern(f"historical:{market}:{state}:*")
    await cache_delete_pattern("availability")
    return results


@app.post("/test/run-mcp-scraper")
async def test_run_mcp_scraper(
    _=Depends(require_admin),
):
    """Manually trigger the full scheduled scraper job, including RTM backfill — for testing only."""
    await run_mcp_scraper()
    return {"status": "triggered — check logs for details"}


@app.post("/test/fetch-weather")
async def test_fetch_weather(
    state: str = Query("Telangana"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Manually trigger weather fetch — for testing only."""
    result = await fetch_tomorrow_weather(db, state=state)
    return result

@app.post("/test/run-pipeline")
async def test_run_pipeline(
    _=Depends(require_admin),
):
    """
    Manually trigger the full scheduled pipeline job (run_pipeline from
    scheduler.py) — all markets × all states, with the same retry +
    per-attempt-timeout logic and cache invalidation as the 9:45 AM cron.
 
    Calls the SAME function the scheduler runs, rather than a separately
    maintained copy of the pipeline logic — so this endpoint can never
    drift out of sync with what actually runs in production.
    """
    await run_pipeline()
    return {"status": "triggered — check logs for details"}