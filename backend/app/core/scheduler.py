import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.database import AsyncSessionLocal
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Active states and markets ────────────────────────────────────────────────
# ACTIVE_STATES: add new states here when expanding
# ACTIVE_MARKETS: all 3 markets must be scraped (cross-market features needed)

ACTIVE_STATES  = ["Telangana"]
ACTIVE_MARKETS = ["GDAM", "DAM", "RTM"]


# ─── Job 1: MCP scraper ───────────────────────────────────────────────────────

async def run_mcp_scraper():
    """
    Scrapes today's data for all markets × all states.
    Runs sequentially: one market per state at a time.
    Runs at 9:00 IST daily.
    """
    logger.info(
        f"[Scheduler] MCP scrape starting — "
        f"states: {ACTIVE_STATES}, markets: {ACTIVE_MARKETS}"
    )
    for state in ACTIVE_STATES:
        for market in ACTIVE_MARKETS:
            async with AsyncSessionLocal() as db:
                try:
                    from app.services.scraper import scrape_today_mcp
                    result = await scrape_today_mcp(
                        db, market=market, state=state
                    )
                    logger.info(
                        f"[Scheduler] Scraped {market}/{state}: {result}"
                    )
                except Exception as e:
                    logger.error(
                        f"[Scheduler] Scrape failed {market}/{state}: {e}"
                    )


# ─── Job 2: Weather fetch ─────────────────────────────────────────────────────

async def run_weather_fetch():
    """
    Fetches tomorrow's weather for all states.
    Runs at 9:45 IST daily.
    """
    logger.info(f"[Scheduler] Weather fetch starting — states: {ACTIVE_STATES}")
    for state in ACTIVE_STATES:
        async with AsyncSessionLocal() as db:
            try:
                from app.services.weather import fetch_tomorrow_weather
                result = await fetch_tomorrow_weather(db, state=state)
                logger.info(f"[Scheduler] Weather {state}: {result}")
            except Exception as e:
                logger.error(f"[Scheduler] Weather failed {state}: {e}")


# ─── Job 3: Feature builder + ML pipeline ────────────────────────────────────

async def run_pipeline():
    """
    Assembles CSV from all market data + weather,
    calls ML service, saves P10/P50/P90 predictions.
    Runs at 9:55 IST daily — after scraper and weather complete.
    """
    logger.info(f"[Scheduler] Pipeline starting — states: {ACTIVE_STATES}")
    for state in ACTIVE_STATES:
        async with AsyncSessionLocal() as db:
            try:
                from app.services.feature_builder import build_features_and_predict
                result = await build_features_and_predict(
                    db, state=state, target_market="GDAM"
                )
                logger.info(f"[Scheduler] Pipeline {state}: {result}")
            except Exception as e:
                logger.error(f"[Scheduler] Pipeline failed {state}: {e}")


# ─── Scheduler setup ──────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        run_mcp_scraper,
        trigger=CronTrigger(hour=9, minute=0),
        id="mcp_scraper",
        name="MCP Scraper — all markets × all states",
        replace_existing=True,
    )

    scheduler.add_job(
        run_weather_fetch,
        trigger=CronTrigger(hour=9, minute=45),
        id="weather_fetch",
        name="Weather Fetch — all states",
        replace_existing=True,
    )

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=9, minute=55),
        id="pipeline",
        name="Feature Builder + ML Pipeline",
        replace_existing=True,
    )

    logger.info(
        "[Scheduler] 3 jobs scheduled — "
        "Scraper 00:30, Weather 00:45, Pipeline 00:55 (IST)"
    )

    return scheduler