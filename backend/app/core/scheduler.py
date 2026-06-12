import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.database import AsyncSessionLocal
from app.core.config import get_settings
import pytz
logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Active states and markets ────────────────────────────────────────────────
# ACTIVE_STATES:  add new states here when expanding
# ACTIVE_MARKETS: all 3 must be scraped (cross-market features needed)
# FORECAST_MARKETS: markets that have a real or mock ML service configured

ACTIVE_STATES    = ["Telangana"]
ACTIVE_MARKETS   = ["GDAM", "DAM", "RTM"]
FORECAST_MARKETS = ["GDAM", "DAM", "RTM"]
IST = pytz.timezone("Asia/Kolkata")

# ─── Job 1: MCP scraper ───────────────────────────────────────────────────────

async def run_mcp_scraper():
    for state in ACTIVE_STATES:
        for market in ACTIVE_MARKETS:
            async with AsyncSessionLocal() as db:
                try:
                    from app.services.scraper import scrape_today_mcp
                    from app.core.redis import cache_delete_pattern

                    result = await scrape_today_mcp(db, market=market, state=state)
                    logger.info(f"[Scheduler] Scraped {market}/{state}: {result}")

                    await cache_delete_pattern(f"historical:{market}:{state}:*")
                    await cache_delete_pattern("availability")

                except Exception as e:
                    logger.error(f"[Scheduler] Scrape failed {market}/{state}: {e}")


# ─── Job 2: Weather fetch ─────────────────────────────────────────────────────

async def run_weather_fetch():
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
    logger.info(
        f"[Scheduler] Pipeline starting — "
        f"states: {ACTIVE_STATES}, markets: {FORECAST_MARKETS}"
    )
    for state in ACTIVE_STATES:
        for market in FORECAST_MARKETS:
            async with AsyncSessionLocal() as db:
                try:
                    from app.services.feature_builder import build_features_and_predict
                    from app.core.redis import cache_delete_pattern

                    result = await build_features_and_predict(
                        db, state=state, target_market=market
                    )
                    logger.info(f"[Scheduler] Pipeline {market}/{state}: {result}")

                    # Only invalidate cache on success — avoid poisoning on failure
                    if result.get("status") == "success":
                        await cache_delete_pattern(f"forecast:{market}:{state}:*")
                        await cache_delete_pattern("availability")
                        logger.info(f"[Scheduler] Cache invalidated for {market}/{state}")
                    else:
                        logger.warning(
                            f"[Scheduler] Pipeline returned non-success for "
                            f"{market}/{state} — cache not cleared: {result.get('error')}"
                        )

                except Exception as e:
                    logger.error(f"[Scheduler] Pipeline failed {market}/{state}: {e}")


# ─── Scheduler setup ──────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        run_mcp_scraper,
        trigger=CronTrigger(hour=9, minute=0, timezone=IST),
        id="mcp_scraper",
        name="MCP Scraper — all markets × all states",
        replace_existing=True,
    )

    # scheduler.add_job(
    #     run_weather_fetch,
    #     trigger=CronTrigger(hour=9, minute=25),
    #     id="weather_fetch",
    #     name="Weather Fetch — all states",
    #     replace_existing=True,
    # )

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=9, minute=30, timezone=IST),
        id="pipeline",
        name="Feature Builder + ML Pipeline — all markets × all states",
        replace_existing=True,
    )

    logger.info(
        "[Scheduler] 3 jobs scheduled — "
        "Scraper 19:20, Weather 19:25, Pipeline 19:30 (IST)"
    )

    return scheduler