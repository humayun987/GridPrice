import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.database import AsyncSessionLocal
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Job functions ────────────────────────────────────────────────────────────

async def run_mcp_scraper():
    """
    Job 1 — Scrapes today's MCP data.
    Writes 96 rows to historical_prices.
    Runs at 00:30 IST daily.
    """
    logger.info("[Scheduler] Starting MCP scrape job...")
    async with AsyncSessionLocal() as db:
        try:
            from app.services.scraper import scrape_today_mcp
            result = await scrape_today_mcp(db)
            logger.info(f"[Scheduler] MCP scrape done: {result}")
        except Exception as e:
            logger.error(f"[Scheduler] MCP scrape failed: {e}")


async def run_weather_fetch():
    """
    Job 2 — Fetches tomorrow's hourly weather.
    Writes 24 rows to raw_weather_forecasts.
    Runs at 00:35 IST daily.
    """
    logger.info("[Scheduler] Starting weather fetch job...")
    async with AsyncSessionLocal() as db:
        try:
            from app.services.weather import fetch_tomorrow_weather
            result = await fetch_tomorrow_weather(db)
            logger.info(f"[Scheduler] Weather fetch done: {result}")
        except Exception as e:
            logger.error(f"[Scheduler] Weather fetch failed: {e}")


# ─── Scheduler setup ──────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    """
    Creates and configures the APScheduler instance.
    Both dev and prod use the same IST schedule.
    Use IntervalTrigger(minutes=2) temporarily when testing scheduler.
    """
    scheduler = AsyncIOScheduler(
        timezone="Asia/Kolkata"
    )

    # Job 1 — MCP scraper at 00:30 IST
    scheduler.add_job(
        run_mcp_scraper,
        trigger=CronTrigger(hour=0, minute=30),
        id="mcp_scraper",
        name="MCP Scraper",
        replace_existing=True,
    )

    # Job 2 — Weather fetch at 00:35 IST
    scheduler.add_job(
        run_weather_fetch,
        trigger=CronTrigger(hour=0, minute=35),
        id="weather_fetch",
        name="Weather Fetch",
        replace_existing=True,
    )

    logger.info(
        "[Scheduler] Jobs scheduled — "
        "MCP at 00:30 IST, Weather at 00:35 IST"
    )

    return scheduler