import asyncio
import uuid
import os
import sys
import pandas as pd
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from app.core.config import get_settings

settings = get_settings()

URL = "https://iexrtmprice.com/DSM_Data/"

# Thread pool — only used on Windows
_executor = ThreadPoolExecutor(max_workers=2)


# ─── Browser scraping logic (sync) ───────────────────────────────────────────

def _scrape_sync(market: str, state: str, scrape_date: str, temp_file: str) -> dict:
    """
    Runs Playwright synchronously.
    Used on Windows (dev) via thread pool.
    Used on Linux (prod) directly since Linux supports sync_playwright fine too.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print(f"[Scraper] Opening {URL}...")
            page.goto(URL, timeout=90000)
            page.wait_for_load_state("networkidle")

            print(f"[Scraper] Selecting market: {market}...")
            page.select_option('select[name="segment"]', label=market)

            print(f"[Scraper] Selecting state: {state}...")
            page.locator('button[data-id="mySelect"]').click()
            page.locator(
                f'.dropdown-menu.show >> text="{state}"'
            ).first.click()

            print(f"[Scraper] Setting date to: {scrape_date}...")
            page.locator('#fromDate').fill(scrape_date)
            page.locator('#toDate').fill(scrape_date)

            print("[Scraper] Submitting search...")
            page.locator('#submit_btn').click()

            print("[Scraper] Waiting for CSV button...")
            csv_button = page.locator('.buttons-csv')
            csv_button.wait_for(state="visible", timeout=60000)

            print("[Scraper] Downloading CSV...")
            with page.expect_download() as download_info:
                csv_button.click()

            download = download_info.value
            download.save_as(temp_file)
            print(f"[Scraper] CSV saved as {temp_file}")
            return {"success": True}

        except Exception as e:
            print(f"[Scraper] Browser error: {e}")
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
        print(f"[Scraper] RAW columns: {list(df.columns)}")
        print(f"[Scraper] First row: {df.iloc[0].to_dict() if len(df) > 0 else 'empty'}")
        print(f"[Scraper] Total rows: {len(df)}")

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
                print(f"[Scraper] Skipping row: {row_error}")
                continue

        await db.commit()
        print(f"[Scraper] Successfully wrote {rows_written} rows")

    except Exception as e:
        error_message = str(e)
        print(f"[Scraper] Failed: {error_message}")
        await db.rollback()

    finally:
        # Always clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"[Scraper] Cleaned up {temp_file}")

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
        print(f"[Scraper] Failed to log run: {e}")