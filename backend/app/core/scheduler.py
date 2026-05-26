import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.database import AsyncSessionLocal
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Active states ────────────────────────────────────────────────────────────
# Add new states here when expanding.
# Scraper, weather, and pipeline all loop over this list automatically.

ACTIVE_STATES = ["Telangana"]


# ─── Job functions ────────────────────────────────────────────────────────────

async def run_mcp_scraper():
    """
    Job 1 — Scrapes today's MCP data for all active states.
    States run sequentially — one after another.
    Runs at 00:30 IST daily. 15 min window before weather job.
    """
    logger.info(f"[Scheduler] MCP scrape starting for: {ACTIVE_STATES}")
    for state in ACTIVE_STATES:
        async with AsyncSessionLocal() as db:
            try:
                from app.services.scraper import scrape_today_mcp
                result = await scrape_today_mcp(db, state=state)
                logger.info(f"[Scheduler] MCP scrape {state}: {result}")
            except Exception as e:
                logger.error(
                    f"[Scheduler] MCP scrape failed for {state}: {e}"
                )


async def run_weather_fetch():
    """
    Job 2 — Fetches tomorrow's weather for all active states.
    States run sequentially.
    Runs at 00:45 IST daily. 10 min window before pipeline job.
    """
    logger.info(f"[Scheduler] Weather fetch starting for: {ACTIVE_STATES}")
    for state in ACTIVE_STATES:
        async with AsyncSessionLocal() as db:
            try:
                from app.services.weather import fetch_tomorrow_weather
                result = await fetch_tomorrow_weather(db, state=state)
                logger.info(f"[Scheduler] Weather {state}: {result}")
            except Exception as e:
                logger.error(
                    f"[Scheduler] Weather failed for {state}: {e}"
                )


async def run_pipeline():
    """
    Job 3 — Builds features and predicts for all active states.
    States run sequentially.
    Runs at 00:55 IST daily — after scraper and weather are done.
    """
    logger.info(f"[Scheduler] Pipeline starting for: {ACTIVE_STATES}")
    for state in ACTIVE_STATES:
        async with AsyncSessionLocal() as db:
            try:
                from app.services.feature_builder import build_features_and_predict
                result = await build_features_and_predict(db, state=state)
                logger.info(f"[Scheduler] Pipeline {state}: {result}")
            except Exception as e:
                logger.error(
                    f"[Scheduler] Pipeline failed for {state}: {e}"
                )


# ─── Scheduler setup ──────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    """
    Creates APScheduler with 3 daily IST jobs.
    Gaps between jobs allow for multi-state sequential processing.
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    # Job 1 — MCP scraper at 00:30 IST
    scheduler.add_job(
        run_mcp_scraper,
        trigger=CronTrigger(hour=0, minute=30),
        id="mcp_scraper",
        name="MCP Scraper",
        replace_existing=True,
    )

    # Job 2 — Weather fetch at 00:45 IST (15 min after scraper)
    scheduler.add_job(
        run_weather_fetch,
        trigger=CronTrigger(hour=0, minute=45),
        id="weather_fetch",
        name="Weather Fetch",
        replace_existing=True,
    )

    # Job 3 — Pipeline at 00:55 IST (10 min after weather)
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=0, minute=55),
        id="pipeline",
        name="Feature Builder + ML Pipeline",
        replace_existing=True,
    )

    logger.info(
        "[Scheduler] 3 jobs scheduled — "
        "Scraper 00:30, Weather 00:45, Pipeline 00:55 (all IST)"
    )

    return scheduler