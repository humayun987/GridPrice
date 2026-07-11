import asyncio
import uuid
import os
import sys
import logging
import pandas as pd
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

URL = "https://iexrtmprice.com/DSM_Data/"

# Thread pool — only used on Windows
_executor = ThreadPoolExecutor(max_workers=2)

# Minimum acceptable rows for a scrape to be considered valid.
# GDAM/DAM expect 96 (15-min blocks/day); RTM's normal same-day scrape
# only has ~40 available at 9AM (rest backfilled later), so this floor
# is set low enough to allow that but still catch a genuinely empty/
# malformed CSV (0 rows) being logged as a false "success".
MIN_EXPECTED_ROWS = 1


# ─── Browser scraping logic (sync) ───────────────────────────────────────────

def _scrape_sync(market: str, state: str, scrape_date: str, temp_file: str) -> dict:
    """
    Runs Playwright synchronously.
    Used on Windows (dev) via thread pool.
    Used on Linux (prod) directly since Linux supports sync_playwright fine too.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        page = browser.new_page()

        try:
            logger.info(f"[Scraper] Opening {URL}...")
            response = page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            if response is None:
                raise RuntimeError("No response received from IEX")

            if not response.ok:
                raise RuntimeError(f"IEX returned HTTP {response.status}")

            logger.info(f"[Scraper] Page loaded, HTTP {response.status}")

            page.locator('select[name="segment"]').wait_for(
                state="visible",
                timeout=30000,
            )

            logger.info(f"[Scraper] Selecting market: {market}...")
            page.select_option('select[name="segment"]', label=market)

            logger.info(f"[Scraper] Selecting state: {state}...")
            page.locator('button[data-id="mySelect"]').click()
            page.locator(
                f'.dropdown-menu.show >> text="{state}"'
            ).first.click()

            logger.info(f"[Scraper] Setting date to: {scrape_date}...")
            page.locator('#fromDate').fill(scrape_date)
            page.locator('#toDate').fill(scrape_date)

            logger.info("[Scraper] Submitting search...")
            page.locator('#submit_btn').click()

            logger.info("[Scraper] Waiting for CSV button...")
            csv_button = page.locator('.buttons-csv')
            csv_button.wait_for(state="visible", timeout=60000)

            logger.info("[Scraper] Downloading CSV...")
            with page.expect_download() as download_info:
                csv_button.click()

            download = download_info.value
            download.save_as(temp_file)
            logger.info(f"[Scraper] CSV saved as {temp_file}")
            return {"success": True}

        except Exception as e:
            logger.error(f"[Scraper] Browser error: {e}")
            return {"success": False, "error": str(e)}

        finally:
            browser.close()


# ─── Main scraper function ────────────────────────────────────────────────────

async def scrape_today_mcp(
    db: AsyncSession,
    market: str = "GDAM",
    state: str = "Telangana",
    target_date: str | None = None,
) -> dict:
    """
    Scrapes today's market data from iexrtmprice.com.
    Writes results to historical_prices table.
    Logs run to scrape_run_logs.

    Works on both Windows (dev) and Linux (prod) automatically.
    """
    started_at = datetime.utcnow()
    rows_written = 0
    error_message = None
    if target_date:
        scrape_date = target_date
    else:
        scrape_date = datetime.now(ZoneInfo("Asia/Kolkata")).strftime('%Y-%m-%d')
    temp_file = f"temp_scrape_{market}_{state}_{scrape_date}.csv"
    try:
        # ── Step 1: Run browser scraping ──────────────────────
        # On Windows — run in thread pool to avoid event loop restriction
        # On Linux  — run in thread pool too for consistency
        # sync_playwright works correctly in threads on both platforms
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            _scrape_sync,
            market,
            state,
            scrape_date,
            temp_file
        )

        if not result.get("success"):
            raise Exception(result.get("error", "Browser scraping failed"))

        # ── Step 2: Parse CSV ─────────────────────────────────
        df = pd.read_csv(temp_file)
        logger.info(f"[Scraper] RAW columns: {list(df.columns)}")
        logger.info(f"[Scraper] First row: {df.iloc[0].to_dict() if len(df) > 0 else 'empty'}")
        logger.info(f"[Scraper] Total rows: {len(df)}")

        # ── Guard: reject an empty/malformed CSV outright ─────
        # A CSV that downloaded fine but parsed to 0 rows (e.g. IEX
        # returned a "no data" page instead of real data, or the page
        # layout changed silently) would otherwise fall through to
        # "Successfully wrote 0 rows" and get logged as a false success —
        # the exact same class of bug that hit the weather job.
        if len(df) < MIN_EXPECTED_ROWS:
            raise ValueError(
                f"Scraped CSV for {market}/{state} on {scrape_date} has "
                f"{len(df)} rows — treating as failed scrape."
            )

        # Clean column names
        df.columns = [
            str(c).strip().lower()
            .replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace(".", "")
            .replace("/", "_")
            for c in df.columns
        ]

        # ── Step 3: Write to historical_prices ────────────────
        for _, row in df.iterrows():
            try:
                # Parse time period — format "00:00-00:15"
                time_str = str(row.get("time_period", "00:00-00:15"))
                start_time = time_str.split("-")[0].strip()
                hour = int(start_time.split(":")[0])
                minute = int(start_time.split(":")[1])

                delivery_date = str(row.get("delivery_date", scrape_date))
                try:
                    base_date = datetime.strptime(delivery_date.strip(), "%d/%m/%Y")
                except ValueError:
                    try:
                        base_date = datetime.strptime(delivery_date.strip(), "%Y-%m-%d")
                    except Exception:
                        base_date = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
                datetime_block = base_date.replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )

                await db.execute(
                    text("""
                        INSERT INTO historical_prices
                        (id, market, region, datetime_block,
                         cleared_buy_mw, cleared_sell_mw,
                         mcp_rs_mwh, created_at)
                        VALUES
                        (:id, :market, :region, :datetime_block,
                         :cleared_buy_mw, :cleared_sell_mw,
                         :mcp_rs_mwh, :created_at)
                        ON CONFLICT (market, region, datetime_block)
                        DO UPDATE SET
                            cleared_buy_mw = EXCLUDED.cleared_buy_mw,
                            cleared_sell_mw = EXCLUDED.cleared_sell_mw,
                            mcp_rs_mwh = EXCLUDED.mcp_rs_mwh,
                            created_at = EXCLUDED.created_at
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "market": market,
                        "region": state,
                        "datetime_block": datetime_block,
                        "cleared_buy_mw": _safe_float(row, "cleared_buy_mw"),
                        "cleared_sell_mw": _safe_float(row, "cleared_sell_mw"),
                        "mcp_rs_mwh": _safe_float(row, "price_rs_mwh"),
                        "created_at": datetime.utcnow(),
                    }
                )
                rows_written += 1

            except Exception as row_error:
                logger.warning(f"[Scraper] Skipping row: {row_error}")
                continue

        # ── Guard: every row failed to parse individually ─────
        # The CSV had rows, but per-row parsing (time/date format,
        # column names) rejected all of them — commit would succeed
        # with 0 actual writes, another false-success path.
        if rows_written == 0:
            raise ValueError(
                f"Scraped CSV for {market}/{state} on {scrape_date} had "
                f"{len(df)} raw rows but 0 were successfully parsed/written."
            )

        await db.commit()
        logger.info(f"[Scraper] Successfully wrote {rows_written} rows")

    except Exception as e:
        error_message = str(e) if str(e) else type(e).__name__
        logger.error(f"[Scraper] Failed: {error_message}")
        await db.rollback()

    finally:
        # Always clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            logger.info(f"[Scraper] Cleaned up {temp_file}")

        # Always log the run
        await _log_scrape_run(
            db=db,
            job_type="mcp_scrape",
            status="success" if not error_message else "failed",
            rows_written=rows_written,
            error_message=error_message,
            started_at=started_at,
        )

    return {
        "status": "success" if not error_message else "failed",
        "rows_written": rows_written,
        "error": error_message,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(row, column: str) -> float:
    """Safely converts a row value to float."""
    try:
        val = row.get(column, 0)
        if val is None or str(val).strip() in ("", "-", "nan"):
            return 0.0
        return float(str(val).replace(",", ""))
    except Exception:
        return 0.0


async def _log_scrape_run(
    db: AsyncSession,
    job_type: str,
    status: str,
    rows_written: int,
    error_message: str | None,
    started_at: datetime,
) -> None:
    """Writes a record to scrape_run_logs."""
    try:
        await db.execute(
            text("""
                INSERT INTO scrape_run_logs
                (id, job_type, status, rows_written,
                 error_message, started_at, completed_at)
                VALUES
                (:id, :job_type, :status, :rows_written,
                 :error_message, :started_at, :completed_at)
            """),
            {
                "id": str(uuid.uuid4()),
                "job_type": job_type,
                "status": status,
                "rows_written": rows_written,
                "error_message": error_message,
                "started_at": started_at,
                "completed_at": datetime.utcnow(),
            }
        )
        await db.commit()
    except Exception as e:
        # This is the run-logging path itself failing (e.g. DB hiccup).
        # Previously this used print(), which meant a failure here could
        # go unnoticed and leave you with zero record of what happened.
        # Also roll back so a failed log-insert can't leave the session
        # in a broken state for any caller that reuses `db` afterward.
        logger.error(f"[Scraper] Failed to log run to scrape_run_logs: {e}")
        try:
            await db.rollback()
        except Exception:
            pass