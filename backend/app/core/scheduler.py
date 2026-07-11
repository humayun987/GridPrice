import logging
import asyncio
from datetime import datetime
from datetime import timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
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

# Per-attempt hard timeout so a hung request/DB call can never silently
# eat a retry slot without a log line. Without this, a stalled event loop
# on the shared B1 instance could keep an attempt "in flight" indefinitely
# with no exception ever raised.
ATTEMPT_TIMEOUT_SECONDS = 150

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

                        result = await asyncio.wait_for(
                            scrape_today_mcp(db, market=market, state=state),
                            timeout=ATTEMPT_TIMEOUT_SECONDS,
                        )

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

                    except asyncio.TimeoutError:
                        logger.error(
                            f"[Scheduler] Scrape attempt {attempt}/{MAX_RETRIES} "
                            f"TIMED OUT after {ATTEMPT_TIMEOUT_SECONDS}s for {market}/{state}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        else:
                            logger.error(
                                f"[Scheduler] Scrape FINAL FAILURE for {market}/{state} "
                                f"after {MAX_RETRIES} attempts (timeout)"
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

                    result = await asyncio.wait_for(
                        scrape_today_mcp(
                            db, market="RTM", state=state, target_date=yesterday
                        ),
                        timeout=ATTEMPT_TIMEOUT_SECONDS,
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

                except asyncio.TimeoutError:
                    logger.error(
                        f"[Scheduler] RTM backfill attempt {attempt}/{MAX_RETRIES} "
                        f"TIMED OUT after {ATTEMPT_TIMEOUT_SECONDS}s for {state}/{yesterday}"
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logger.error(
                            f"[Scheduler] RTM backfill FINAL FAILURE {state}/{yesterday} "
                            f"after {MAX_RETRIES} attempts (timeout)"
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
                    result = await asyncio.wait_for(
                        fetch_tomorrow_weather(db, state=state),
                        timeout=ATTEMPT_TIMEOUT_SECONDS,
                    )

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

                except asyncio.TimeoutError:
                    logger.error(
                        f"[Scheduler] Weather attempt {attempt}/{MAX_RETRIES} "
                        f"TIMED OUT after {ATTEMPT_TIMEOUT_SECONDS}s for {state}"
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        logger.error(
                            f"[Scheduler] Weather FINAL FAILURE {state} "
                            f"after {MAX_RETRIES} attempts (timeout)"
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

                        result = await asyncio.wait_for(
                            build_features_and_predict(
                                db, state=state, target_market=market
                            ),
                            timeout=ATTEMPT_TIMEOUT_SECONDS,
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

                    except asyncio.TimeoutError:
                        logger.error(
                            f"[Scheduler] Pipeline attempt {attempt}/{MAX_RETRIES} "
                            f"TIMED OUT after {ATTEMPT_TIMEOUT_SECONDS}s for {market}/{state}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        else:
                            logger.error(
                                f"[Scheduler] Pipeline FINAL FAILURE for {market}/{state} "
                                f"after {MAX_RETRIES} attempts (timeout)"
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

# ─── Scheduler event listeners ────────────────────────────────────────────────

def _job_error_listener(event):
    """
    Safety net: if a scheduled job throws all the way out of its own
    try/except (e.g. cancelled by the loop, killed by the platform),
    this guarantees ONE clear log line instead of the job silently
    vanishing mid-run with no trace, which is what made the weather
    job look "ambiguous" in the Azure log stream.
    """
    logger.error(
        f"[Scheduler] JOB CRASHED — id={event.job_id} "
        f"exception={event.exception!r}"
    )


def _job_missed_listener(event):
    logger.warning(
        f"[Scheduler] JOB MISSED — id={event.job_id} "
        f"scheduled_run_time={event.scheduled_run_time}"
    )


# ─── Scheduler setup ──────────────────────────────────────────────────────────
# Timing note: jobs are spaced with margin so a slow scraper run can't
# bleed into the weather/pipeline slots on the shared single-core B1
# instance. Worst-case scraper runtime (3 markets × up to 3 retries ×
# (~150s timeout + 15s delay) ≈ up to ~20 min) still fits inside the
# scraper→weather gap below with headroom.

def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    scheduler.add_job(
        run_weather_fetch,
        trigger=CronTrigger(hour=7, minute=0, timezone=IST),
        id="weather_fetch",
        name="Weather Fetch — all states",
        replace_existing=True,
        misfire_grace_time=300,
    )
    
    
    scheduler.add_job(
        run_mcp_scraper,
        trigger=CronTrigger(hour=9, minute=0, timezone=IST),
        id="mcp_scraper",
        name="MCP Scraper — all markets × all states",
        replace_existing=True,
        misfire_grace_time=300,
    )


    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=9, minute=45, timezone=IST),
        id="pipeline",
        name="Feature Builder + ML Pipeline — all markets × all states",
        replace_existing=True,
        misfire_grace_time=300,
    )

    scheduler.add_listener(_job_error_listener, EVENT_JOB_ERROR)
    scheduler.add_listener(_job_missed_listener, EVENT_JOB_MISSED)

    logger.info(
        "[Scheduler] 3 jobs scheduled — "
        "Weather 7:00, MCP Scraper 9:00,  Pipeline 9:45 (IST)"
    )

    return scheduler