import uuid
import httpx
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.services.scraper import _log_scrape_run
from zoneinfo import ZoneInfo

STATE_COORDS = {
    "Telangana":      {"lat": 17.3850, "lon": 78.4867},
    "Delhi":          {"lat": 28.6139, "lon": 77.2090},
    "Maharashtra":    {"lat": 19.0760, "lon": 72.8777},
    "Karnataka":      {"lat": 12.9716, "lon": 77.5946},
    "Tamil Nadu":     {"lat": 13.0827, "lon": 80.2707},
    "Gujarat":        {"lat": 23.0225, "lon": 72.5714},
    "West Bengal":    {"lat": 22.5726, "lon": 88.3639},
    "Uttar Pradesh":  {"lat": 26.8467, "lon": 80.9462},
    "Rajasthan":      {"lat": 26.9124, "lon": 75.7873},
    "Madhya Pradesh": {"lat": 23.2599, "lon": 77.4126},
}


async def fetch_tomorrow_weather(
    db: AsyncSession,
    state: str = "Telangana"
) -> dict:
    """
    Fetches tomorrow's hourly weather for a given state.
    Writes 24 rows to raw_weather_forecasts.
    Includes rain (precipitation) column needed by ML model.
    """
    started_at = datetime.utcnow()
    rows_written = 0
    error_message = None

    tomorrow = (
        datetime.now(ZoneInfo("Asia/Kolkata")).date()
        + timedelta(days=1)
    )

    date_str = tomorrow.strftime("%Y-%m-%d")

    try:
        if state not in STATE_COORDS:
            raise ValueError(f"State '{state}' not in STATE_COORDS.")

        coords = STATE_COORDS[state]

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "latitude":  coords["lat"],
                "longitude": coords["lon"],
                "hourly": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "cloud_cover",
                    "wind_speed_10m",
                    "shortwave_radiation",
                    "rain",                # ← precipitation as rain
                ],
                "start_date": date_str,
                "end_date":   date_str,
                "timezone":   "Asia/Kolkata",
            }

            print(f"[Weather] Fetching for {state} on {date_str}...")
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params
            )
            response.raise_for_status()
            data = response.json()

        hourly = data.get("hourly", {})
        times  = hourly.get("time", [])
        print(f"[Weather] {len(times)} hourly rows received")

        for i, time_str in enumerate(times):
            await db.execute(
                text("""
                    INSERT INTO raw_weather_forecasts
                    (id, region, datetime_hour, temperature,
                     humidity, cloud_cover, wind_speed,
                     solar_irradiance, rain, fetched_at)
                    VALUES
                    (:id, :region, :datetime_hour, :temperature,
                     :humidity, :cloud_cover, :wind_speed,
                     :solar_irradiance, :rain, :fetched_at)
                """),
                {
                    "id":             str(uuid.uuid4()),
                    "region":         state,
                    "datetime_hour":  datetime.fromisoformat(time_str),
                    "temperature":    _safe_get(hourly, "temperature_2m", i),
                    "humidity":       _safe_get(hourly, "relative_humidity_2m", i),
                    "cloud_cover":    _safe_get(hourly, "cloud_cover", i),
                    "wind_speed":     _safe_get(hourly, "wind_speed_10m", i),
                    "solar_irradiance": _safe_get(hourly, "shortwave_radiation", i),
                    "rain":           _safe_get(hourly, "rain", i),
                    "fetched_at":     datetime.utcnow(),
                }
            )
            rows_written += 1

        await db.commit()
        print(f"[Weather] Wrote {rows_written} rows for {state}")

    except Exception as e:
        error_message = str(e)
        print(f"[Weather] Failed: {error_message}")
        await db.rollback()

    finally:
        await _log_scrape_run(
            db=db,
            job_type="weather_fetch",
            status="success" if not error_message else "failed",
            rows_written=rows_written,
            error_message=error_message,
            started_at=started_at,
        )

    return {
        "status":       "success" if not error_message else "failed",
        "rows_written": rows_written,
        "error":        error_message,
    }


async def fetch_weather_range(
    state: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """
    Fetches hourly weather for any date range from Open-Meteo.
    Uses archive API for past dates, forecast API for future.
    Returns list of dicts — one per hour.
    Used by feature_builder to get historical weather for CSV assembly.
    """
    if state not in STATE_COORDS:
        return []

    coords = STATE_COORDS[state]

    # Use archive API for past, forecast API for today/future
    today = datetime.now(
        ZoneInfo("Asia/Kolkata")
    ).date()

    start = date.fromisoformat(start_date)

    if start < today:
        base_url = "https://archive-api.open-meteo.com/v1/archive"
    else:
        base_url = "https://api.open-meteo.com/v1/forecast"

    async with httpx.AsyncClient(timeout=60.0) as client:
        params = {
            "latitude":  coords["lat"],
            "longitude": coords["lon"],
            "hourly": [
                "temperature_2m",
                "relative_humidity_2m",
                "cloud_cover",
                "wind_speed_10m",
                "shortwave_radiation",
                "rain",
            ],
            "start_date": start_date,
            "end_date":   end_date,
            "timezone":   "Asia/Kolkata",
        }

        response = await client.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

    hourly = data.get("hourly", {})
    times  = hourly.get("time", [])

    rows = []
    for i, time_str in enumerate(times):
        rows.append({
            "datetime_hour":    datetime.fromisoformat(time_str),
            "temperature":      _safe_get(hourly, "temperature_2m", i) or 0.0,
            "humidity":         _safe_get(hourly, "relative_humidity_2m", i) or 0.0,
            "cloud_cover":      _safe_get(hourly, "cloud_cover", i) or 0.0,
            "wind_speed":       _safe_get(hourly, "wind_speed_10m", i) or 0.0,
            "solar_irradiance": _safe_get(hourly, "shortwave_radiation", i) or 0.0,
            "rain":             _safe_get(hourly, "rain", i) or 0.0,
        })

    return rows


def _safe_get(hourly: dict, key: str, index: int) -> float | None:
    try:
        val = hourly.get(key, [])[index]
        return float(val) if val is not None else None
    except Exception:
        return None