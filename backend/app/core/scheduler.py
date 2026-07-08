import logging
import asyncio
from datetime import datetime
from datetime import timedelta
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
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 15

    for state in ACTIVE_STATES:
        for market in ACTIVE_MARKETS:
            for attempt in range(1, MAX_RETRIES + 1):
                async with AsyncSessionLocal() as db:
                    try:
                        from app.services.scraper import scrape_today_mcp
                        from app.core.redis import cache_delete_pattern

                        result = await scrape_today_mcp(db, market=market, state=state)

                        if result.get("status") == "success":
                            logger.info(f"[Scheduler] Scraped {market}/{state}: {result}")
                            await cache_delete_pattern(f"historical:{market}:{state}:*")
                            await cache_delete_pattern("availability")
                            break

                        else:
                            logger.warning(
                                f"[Scheduler] Scrape attempt {attempt}/{MAX_RETRIES} "
                                f"failed for {market}/{state}: {result.get('error')}"
                            )
                            if attempt < MAX_RETRIES:
                                await asyncio.sleep(RETRY_DELAY_SECONDS)
                            else:
                                logger.error(
                                    f"[Scheduler] Scrape FINAL FAILURE for {market}/{state} "
                                    f"after {MAX_RETRIES} attempts: {result.get('error')}"
                                )

                    except Exception as e:
                        logger.error(
                            f"[Scheduler] Scrape attempt {attempt}/{MAX_RETRIES} "
                            f"exception {market}/{state}: {e}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        else:
                            logger.error(
                                f"[Scheduler] Scrape FINAL FAILURE for {market}/{state} "
                                f"after {MAX_RETRIES} attempts (exception): {e}"
                            )

    # RTM backfill — same retry pattern
    yesterday = (datetime.now(IST) - timedelta(days=1)).strftime('%Y-%m-%d')
    for state in ACTIVE_STATES:
        for attempt in range(1, MAX_RETRIES + 1):
            async with AsyncSessionLocal() as db:
                try:
                    from app.services.scraper import scrape_today_mcp
                    from app.core.redis import cache_delete_pattern

                    result = await scrape_today_mcp(
                        db, market="RTM", state=state, target_date=yesterday
                    )

                    if result.get("status") == "success":
                        logger.info(f"[Scheduler] RTM backfill {state} for {yesterday}: {result}")
                        await cache_delete_pattern(f"historical:RTM:{state}:*")
                        await cache_delete_pattern("availability")
                        break
                    else:
                        logger.warning(
                            f"[Scheduler] RTM backfill attempt {attempt}/{MAX_RETRIES} "
                            f"failed {state}/{yesterday}: {result.get('error')}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        else:
                            logger.error(
                                f"[Scheduler] RTM backfill FINAL FAILURE {state}/{yesterday} "
                                f"after {MAX_RETRIES} attempts: {result.get('error')}"
                            )

                except Exception as e:
                    logger.error(
                        f"[Scheduler] RTM backfill attempt {attempt}/{MAX_RETRIES} "
                        f"exception {state}/{yesterday}: {e}"
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logger.error(
                            f"[Scheduler] RTM backfill FINAL FAILURE {state}/{yesterday} "
                            f"after {MAX_RETRIES} attempts (exception): {e}"
                        )       
# ─── Job 2: Weather fetch ─────────────────────────────────────────────────────

async def run_weather_fetch():
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 15

    logger.info(f"[Scheduler] Weather fetch starting — states: {ACTIVE_STATES}")
    for state in ACTIVE_STATES:
        for attempt in range(1, MAX_RETRIES + 1):
            async with AsyncSessionLocal() as db:
                try:
                    from app.services.weather import fetch_tomorrow_weather
                    result = await fetch_tomorrow_weather(db, state=state)

                    if result.get("status") == "success":
                        logger.info(f"[Scheduler] Weather {state}: {result}")
                        break
                    else:
                        logger.warning(
                            f"[Scheduler] Weather attempt {attempt}/{MAX_RETRIES} "
                            f"failed {state}: {result.get('error')}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        else:
                            logger.error(
                                f"[Scheduler] Weather FINAL FAILURE {state} "
                                f"after {MAX_RETRIES} attempts: {result.get('error')}"
                            )

                except Exception as e:
                    logger.error(
                        f"[Scheduler] Weather attempt {attempt}/{MAX_RETRIES} "
                        f"exception {state}: {e}"
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logger.error(
                            f"[Scheduler] Weather FINAL FAILURE {state} "
                            f"after {MAX_RETRIES} attempts (exception): {e}"
                        )

# ─── Job 3: Feature builder + ML pipeline ────────────────────────────────────

async def run_pipeline():
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 15

    logger.info(
        f"[Scheduler] Pipeline starting — "
        f"states: {ACTIVE_STATES}, markets: {FORECAST_MARKETS}"
    )
    for state in ACTIVE_STATES:
        for market in FORECAST_MARKETS:
            for attempt in range(1, MAX_RETRIES + 1):
                async with AsyncSessionLocal() as db:
                    try:
                        from app.services.feature_builder import build_features_and_predict
                        from app.core.redis import cache_delete_pattern

                        result = await build_features_and_predict(
                            db, state=state, target_market=market
                        )

                        if result.get("status") == "success":
                            logger.info(f"[Scheduler] Pipeline {market}/{state}: {result}")
                            await cache_delete_pattern(f"forecast:{market}:{state}:*")
                            await cache_delete_pattern("availability")
                            logger.info(f"[Scheduler] Cache invalidated for {market}/{state}")
                            break

                        else:
                            logger.warning(
                                f"[Scheduler] Pipeline attempt {attempt}/{MAX_RETRIES} "
                                f"failed for {market}/{state}: {result.get('error')}"
                            )
                            if attempt < MAX_RETRIES:
                                await asyncio.sleep(RETRY_DELAY_SECONDS)
                            else:
                                logger.error(
                                    f"[Scheduler] Pipeline FINAL FAILURE for {market}/{state} "
                                    f"after {MAX_RETRIES} attempts: {result.get('error')}"
                                )

                    except Exception as e:
                        logger.error(
                            f"[Scheduler] Pipeline attempt {attempt}/{MAX_RETRIES} "
                            f"exception {market}/{state}: {e}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        else:
                            logger.error(
                                f"[Scheduler] Pipeline FINAL FAILURE for {market}/{state} "
                                f"after {MAX_RETRIES} attempts (exception): {e}"
                            )

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

    scheduler.add_job(
        run_weather_fetch,
        trigger=CronTrigger(hour=9, minute=30, timezone=IST),
        id="weather_fetch",
        name="Weather Fetch — all states",
        replace_existing=True,
    )

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=9, minute=45, timezone=IST),
        id="pipeline",
        name="Feature Builder + ML Pipeline — all markets × all states",
        replace_existing=True,
    )

    logger.info(
        "[Scheduler] 3 jobs scheduled — "
        "Scraper 9:00 (incl. RTM backfill), Weather 9:30, Pipeline 9:45 (IST)"
    )

    return scheduler