"""
Backfill script — scrapes last 7 days of DAM, GDAM, RTM data for Telangana.
Run once manually: python backfill.py

After this, daily scraper handles today's data automatically.
"""
import asyncio
import sys
import uuid
import os
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import AsyncSessionLocal

URL = "https://iexrtmprice.com/DSM_Data/"
ACTIVE_STATES  = ["Telangana"]
ACTIVE_MARKETS = ["GDAM", "DAM", "RTM"]
DAYS_BACK      = 1

_executor = ThreadPoolExecutor(max_workers=2)


def _scrape_sync_date(
    market: str,
    state: str,
    date_str: str,
    temp_file: str
) -> dict:
    """Scrapes data for a specific date."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print(f"  [Browser] Opening {URL}...")
            page.goto(URL, timeout=60000)
            page.wait_for_load_state("networkidle")

            page.select_option('select[name="segment"]', label=market)

            page.locator('button[data-id="mySelect"]').click()
            page.locator(
                f'.dropdown-menu.show >> text="{state}"'
            ).first.click()

            page.locator('#fromDate').fill(date_str)
            page.locator('#toDate').fill(date_str)

            page.locator('#submit_btn').click()

            csv_button = page.locator('.buttons-csv')
            csv_button.wait_for(state="visible", timeout=30000)

            with page.expect_download() as download_info:
                csv_button.click()

            download = download_info.value
            download.save_as(temp_file)
            return {"success": True}

        except Exception as e:
            print(f"  [Browser] Error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            browser.close()


def _safe_float(row, column: str) -> float:
    try:
        val = row.get(column, 0)
        if val is None or str(val).strip() in ("", "-", "nan"):
            return 0.0
        return float(str(val).replace(",", ""))
    except Exception:
        return 0.0


async def scrape_date(
    db: AsyncSession,
    market: str,
    state: str,
    target_date: datetime
) -> int:
    """Scrapes one market for one date. Returns rows written."""
    date_str  = target_date.strftime('%Y-%m-%d')
    temp_file = f"temp_backfill_{market}_{state}_{date_str}.csv"
    rows_written = 0

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, _scrape_sync_date,
            market, state, date_str, temp_file
        )

        if not result.get("success"):
            print(f"  ✗ Browser failed: {result.get('error')}")
            return 0

        df = pd.read_csv(temp_file)

        # Clean column names
        df.columns = [
            str(c).strip().lower()
            .replace(" ", "_").replace("(", "")
            .replace(")", "").replace(".", "").replace("/", "_")
            for c in df.columns
        ]

        for _, row in df.iterrows():
            try:
                time_str   = str(row.get("time_period", "00:00-00:15"))
                start_time = time_str.split("-")[0].strip()
                hour       = int(start_time.split(":")[0])
                minute     = int(start_time.split(":")[1])

                delivery_date = str(row.get("delivery_date", date_str))
                try:
                    base_date = datetime.strptime(
                        delivery_date.strip(), "%Y-%m-%d"
                    )
                except Exception:
                    base_date = target_date

                datetime_block = base_date.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
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
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "id":            str(uuid.uuid4()),
                        "market":        market,
                        "region":        state,
                        "datetime_block": datetime_block,
                        "cleared_buy_mw":  _safe_float(row, "cleared_buy_mw"),
                        "cleared_sell_mw": _safe_float(row, "cleared_sell_mw"),
                        "mcp_rs_mwh":     _safe_float(row, "price_rs_mwh"),
                        "created_at":     datetime.utcnow(),
                    }
                )
                rows_written += 1

            except Exception as row_error:
                print(f"  Row error: {row_error}")
                continue

        await db.commit()

    except Exception as e:
        print(f"  ✗ Failed: {e}")
        await db.rollback()

    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    return rows_written


async def main():
    print("=" * 60)
    print("tatva.gridprice — Historical Backfill")
    print(f"States:  {ACTIVE_STATES}")
    print(f"Markets: {ACTIVE_MARKETS}")
    print(f"Days:    last {DAYS_BACK} days")
    print("=" * 60)

    today = datetime.now().date()

    # Build list of dates — last 7 days excluding today
    dates = [
        datetime.combine(today - timedelta(days=i), datetime.min.time())
        for i in range(1, DAYS_BACK + 1)
    ]
    dates.reverse()  # oldest first

    total_rows = 0

    for state in ACTIVE_STATES:
        for market in ACTIVE_MARKETS:
            print(f"\n── {market} / {state} ──────────────────────")
            for target_date in dates:
                date_str = target_date.strftime('%Y-%m-%d')
                print(f"  Scraping {date_str}...", end=" ", flush=True)

                async with AsyncSessionLocal() as db:
                    rows = await scrape_date(db, market, state, target_date)

                print(f"✓ {rows} rows")
                total_rows += rows

    print("\n" + "=" * 60)
    print(f"Backfill complete — {total_rows} total rows written")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())