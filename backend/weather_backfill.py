# weather_backfill.py
"""
Weather Backfill Script

Backfills:
    - Last 7 days historical weather
    - Today weather
    - Tomorrow weather

Run:
    python weather_backfill.py
"""

import asyncio
import sys
import os
import uuid

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import AsyncSessionLocal
from app.services.weather import fetch_weather_range


ACTIVE_STATES = [
    "Telangana",
]


async def write_weather_rows(
    db: AsyncSession,
    state: str,
    rows: list[dict],
) -> int:

    rows_written = 0

    for row in rows:

        await db.execute(
            text("""
                INSERT INTO raw_weather_forecasts
                (
                    id,
                    region,
                    datetime_hour,
                    temperature,
                    humidity,
                    cloud_cover,
                    wind_speed,
                    solar_irradiance,
                    rain,
                    fetched_at
                )
                VALUES
                (
                    :id,
                    :region,
                    :datetime_hour,
                    :temperature,
                    :humidity,
                    :cloud_cover,
                    :wind_speed,
                    :solar_irradiance,
                    :rain,
                    :fetched_at
                )
            """),
            {
                "id": str(uuid.uuid4()),
                "region": state,
                "datetime_hour": row["datetime_hour"],
                "temperature": row["temperature"],
                "humidity": row["humidity"],
                "cloud_cover": row["cloud_cover"],
                "wind_speed": row["wind_speed"],
                "solar_irradiance": row["solar_irradiance"],
                "rain": row["rain"],
                "fetched_at": datetime.utcnow(),
            }
        )

        rows_written += 1

    await db.commit()

    return rows_written


async def backfill_state(
    db: AsyncSession,
    state: str,
) -> int:

    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    # -----------------------------------------
    # Historical: Last 7 days
    # -----------------------------------------

    historical_start = (
        today - timedelta(days=7)
    ).strftime("%Y-%m-%d")

    historical_end = (
        today - timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print(
        f"  Historical: "
        f"{historical_start} -> {historical_end}"
    )

    historical_rows = await fetch_weather_range(
        state=state,
        start_date=historical_start,
        end_date=historical_end,
    )

    # -----------------------------------------
    # Forecast: Today + Tomorrow
    # -----------------------------------------

    forecast_start = today.strftime("%Y-%m-%d")

    forecast_end = (
        today + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print(
        f"  Forecast: "
        f"{forecast_start} -> {forecast_end}"
    )

    forecast_rows = await fetch_weather_range(
        state=state,
        start_date=forecast_start,
        end_date=forecast_end,
    )

    all_rows = historical_rows + forecast_rows

    print(
        f"  Received {len(all_rows)} hourly rows"
    )

    rows_written = await write_weather_rows(
        db=db,
        state=state,
        rows=all_rows,
    )

    return rows_written


async def main():

    print("=" * 60)
    print("tatva.gridprice — Weather Backfill")
    print(f"States: {ACTIVE_STATES}")
    print("Range : Last 7 Days + Today + Tomorrow")
    print("=" * 60)

    total_rows = 0

    for state in ACTIVE_STATES:

        print(
            f"\n── {state} "
            f"────────────────────────────"
        )

        async with AsyncSessionLocal() as db:

            try:

                rows = await backfill_state(
                    db=db,
                    state=state,
                )

                total_rows += rows

                print(
                    f"✓ Inserted {rows} rows"
                )

            except Exception as e:

                await db.rollback()

                print(
                    f"✗ Failed: {e}"
                )

    print("\n" + "=" * 60)
    print(
        f"Backfill complete — "
        f"{total_rows} rows inserted"
    )
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())