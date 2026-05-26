import uuid
import math
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def build_features_and_predict(
    db: AsyncSession,
    market: str = "GDAM",
    state: str = "Telangana"
) -> dict:
    """
    Full pipeline for one state:
    1. Read historical prices
    2. Read tomorrow's weather
    3. Build 96-block feature payload
    4. Call ML service
    5. Save predictions to DB
    """
    print(f"[Pipeline] Starting for {state} - {market}")

    try:
        # ── Step 1: Historical prices ─────────────────────────
        historical_df = await _fetch_historical_prices(db, state, market)
        if historical_df.empty:
            raise ValueError(
                f"No historical data for {state}. Run scraper first."
            )
        print(f"[Pipeline] Historical rows: {len(historical_df)}")

        # ── Step 2: Tomorrow's weather ────────────────────────
        weather_df = await _fetch_tomorrow_weather(db, state)
        if weather_df.empty:
            raise ValueError(
                f"No weather data for {state}. Run weather fetch first."
            )
        print(f"[Pipeline] Weather rows: {len(weather_df)}")

        # ── Step 3: Build payload ─────────────────────────────
        payload = _build_payload(historical_df, weather_df, market, state)
        print(f"[Pipeline] Payload blocks: {len(payload)}")

        # ── Step 4: Call ML service ───────────────────────────
        from app.services.ml_service import call_ml_service
        predictions = await call_ml_service(payload)
        print(f"[Pipeline] Predictions received: {len(predictions)}")

        # ── Step 5: Save to DB ────────────────────────────────
        forecast_run_id = await _save_predictions(
            db, predictions, market, state
        )
        print(f"[Pipeline] Saved run: {forecast_run_id}")

        return {
            "status": "success",
            "forecast_run_id": forecast_run_id,
            "blocks_predicted": len(predictions),
            "state": state,
            "market": market,
        }

    except Exception as e:
        print(f"[Pipeline] Failed for {state}: {e}")
        return {"status": "failed", "error": str(e), "state": state}


# ─── Fetch historical prices ──────────────────────────────────────────────────

async def _fetch_historical_prices(
    db: AsyncSession,
    state: str,
    market: str
) -> pd.DataFrame:
    """
    Reads last 2 days of MCP data for the state.
    2 days needed for lag_96 (yesterday same time).
    """
    result = await db.execute(
        text("""
            SELECT
                datetime_block,
                mcp_rs_mwh,
                cleared_buy_mw,
                cleared_sell_mw
            FROM historical_prices
            WHERE
                region = :state
                AND market = :market
                AND datetime_block >= NOW() - INTERVAL '2 days'
            ORDER BY datetime_block ASC
        """),
        {"state": state, "market": market}
    )

    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "datetime_block", "mcp_rs_mwh",
        "cleared_buy_mw", "cleared_sell_mw"
    ])

    # Strip timezone info for consistent comparison
    df["datetime_block"] = pd.to_datetime(
        df["datetime_block"]
    ).dt.tz_localize(None)

    df = df.sort_values("datetime_block").reset_index(drop=True)
    return df


# ─── Fetch tomorrow's weather ─────────────────────────────────────────────────

async def _fetch_tomorrow_weather(
    db: AsyncSession,
    state: str
) -> pd.DataFrame:
    """
    Reads tomorrow's 24 hourly weather rows for the state.
    """
    tomorrow = datetime.now().date() + timedelta(days=1)
    tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
    tomorrow_end   = tomorrow_start + timedelta(days=1)

    result = await db.execute(
        text("""
            SELECT
                datetime_hour,
                temperature,
                humidity,
                cloud_cover,
                wind_speed,
                solar_irradiance
            FROM raw_weather_forecasts
            WHERE
                region = :state
                AND datetime_hour >= :start
                AND datetime_hour < :end
            ORDER BY datetime_hour ASC
        """),
        {"state": state, "start": tomorrow_start, "end": tomorrow_end}
    )

    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "datetime_hour", "temperature", "humidity",
        "cloud_cover", "wind_speed", "solar_irradiance"
    ])

    # Strip timezone info for consistent comparison
    df["datetime_hour"] = pd.to_datetime(
        df["datetime_hour"]
    ).dt.tz_localize(None)

    return df


# ─── Build 96-block payload ───────────────────────────────────────────────────

def _build_payload(
    historical_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    market: str,
    state: str
) -> list[dict]:
    """
    Builds 15 features for each of 96 tomorrow blocks.

    Weather is hourly (24 rows) — each hour covers 4 blocks:
      14:00 weather → used for 14:00, 14:15, 14:30, 14:45 blocks
    """
    tomorrow = datetime.now().date() + timedelta(days=1)
    payload = []

    for block_idx in range(96):
        minutes    = block_idx * 15
        block_time = datetime.combine(
            tomorrow, datetime.min.time()
        ) + timedelta(minutes=minutes)

        # ── Lag features ──────────────────────────────────────
        lag_1  = _get_mcp_at(historical_df, block_time - timedelta(minutes=15))
        lag_4  = _get_mcp_at(historical_df, block_time - timedelta(hours=1))
        lag_96 = _get_mcp_at(historical_df, block_time - timedelta(days=1))

        # ── Rolling features ──────────────────────────────────
        rolling_window = _get_rolling_window(historical_df, block_time, n=4)
        rolling_mean_4 = float(rolling_window.mean()) if len(rolling_window) > 0 else lag_1
        rolling_std_4  = float(rolling_window.std())  if len(rolling_window) > 1 else 0.0

        # ── Demand supply ratio ───────────────────────────────
        demand_supply_ratio = _get_demand_supply_ratio(historical_df, block_time)

        # ── Weather features ──────────────────────────────────
        # Round block time DOWN to nearest hour to match weather row
        # e.g. 14:15, 14:30, 14:45 all become 14:00
        block_hour = block_time.replace(minute=0, second=0, microsecond=0)
        weather = _get_weather_for_block(weather_df, block_hour)

        # ── Datetime features ─────────────────────────────────
        hour        = block_time.hour + block_time.minute / 60.0
        hour_sin    = math.sin(2 * math.pi * hour / 24)
        hour_cos    = math.cos(2 * math.pi * hour / 24)
        day_of_week = block_time.weekday()
        is_weekend  = 1 if day_of_week >= 5 else 0

        payload.append({
            "datetime_block":      block_time.isoformat(),
            "market":              market,
            "state":               state,
            "lag_1":               lag_1,
            "lag_4":               lag_4,
            "lag_96":              lag_96,
            "rolling_mean_4":      round(rolling_mean_4, 4),
            "rolling_std_4":       round(rolling_std_4, 4),
            "demand_supply_ratio": demand_supply_ratio,
            "temperature":         weather.get("temperature", 0.0),
            "humidity":            weather.get("humidity", 0.0),
            "cloud_cover":         weather.get("cloud_cover", 0.0),
            "wind_speed":          weather.get("wind_speed", 0.0),
            "solar_irradiance":    weather.get("solar_irradiance", 0.0),
            "hour_sin":            round(hour_sin, 6),
            "hour_cos":            round(hour_cos, 6),
            "day_of_week":         day_of_week,
            "is_weekend":          is_weekend,
        })

    return payload


# ─── Save predictions ─────────────────────────────────────────────────────────

async def _save_predictions(
    db: AsyncSession,
    predictions: list[dict],
    market: str,
    state: str
) -> str:
    """
    Saves 1 forecast_run row and 96 forecast rows.
    Returns forecast_run_id.
    """
    tomorrow        = datetime.now().date() + timedelta(days=1)
    forecast_run_id = str(uuid.uuid4())

    # Write forecast_run
    await db.execute(
        text("""
            INSERT INTO forecast_runs
            (id, market, region, forecast_date,
             model_run_timestamp, status, created_at)
            VALUES
            (:id, :market, :region, :forecast_date,
             :model_run_timestamp, :status, :created_at)
        """),
        {
            "id":                   forecast_run_id,
            "market":               market,
            "region":               state,
            "forecast_date":        tomorrow,
            "model_run_timestamp":  datetime.utcnow(),
            "status":               "completed",
            "created_at":           datetime.utcnow(),
        }
    )

    # Write 96 forecast rows
    for pred in predictions:
        await db.execute(
            text("""
                INSERT INTO forecasts
                (id, forecast_run_id, market, region,
                 datetime_block, predicted_price,
                 lower_ci, upper_ci, confidence_level, created_at)
                VALUES
                (:id, :forecast_run_id, :market, :region,
                 :datetime_block, :predicted_price,
                 :lower_ci, :upper_ci, :confidence_level, :created_at)
            """),
            {
                "id":               str(uuid.uuid4()),
                "forecast_run_id":  forecast_run_id,
                "market":           market,
                "region":           state,
                "datetime_block":   datetime.fromisoformat(pred["datetime_block"]),
                "predicted_price":  pred["predicted_price"],
                "lower_ci":         pred["lower_ci"],
                "upper_ci":         pred["upper_ci"],
                "confidence_level": pred["confidence_level"],
                "created_at":       datetime.utcnow(),
            }
        )

    await db.commit()
    return forecast_run_id


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_mcp_at(df: pd.DataFrame, target_time: datetime) -> float:
    """Gets MCP at exact datetime. Returns 0.0 if not found."""
    match = df[df["datetime_block"] == pd.Timestamp(target_time)]
    if not match.empty:
        return float(match.iloc[0]["mcp_rs_mwh"])
    return 0.0


def _get_rolling_window(
    df: pd.DataFrame,
    block_time: datetime,
    n: int = 4
) -> pd.Series:
    """Gets last N MCP prices before block_time."""
    before = df[df["datetime_block"] < pd.Timestamp(block_time)]
    return before["mcp_rs_mwh"].tail(n)


def _get_demand_supply_ratio(
    df: pd.DataFrame,
    block_time: datetime
) -> float:
    """Gets cleared_buy / cleared_sell from most recent block."""
    before = df[df["datetime_block"] < pd.Timestamp(block_time)]
    if before.empty:
        return 1.0
    latest = before.iloc[-1]
    buy  = float(latest["cleared_buy_mw"]  or 0)
    sell = float(latest["cleared_sell_mw"] or 0)
    if sell == 0:
        return 1.0
    return round(buy / sell, 4)


def _get_weather_for_block(
    weather_df: pd.DataFrame,
    block_hour: datetime      # already rounded to hour
) -> dict:
    """
    Gets weather for a block by matching exact hour.
    block_hour must already be rounded down to the hour.
    4 consecutive blocks share the same weather row.
    """
    match = weather_df[
        weather_df["datetime_hour"] == pd.Timestamp(block_hour)
    ]
    if not match.empty:
        row = match.iloc[0]
        return {
            "temperature":      float(row["temperature"]      or 0),
            "humidity":         float(row["humidity"]          or 0),
            "cloud_cover":      float(row["cloud_cover"]       or 0),
            "wind_speed":       float(row["wind_speed"]        or 0),
            "solar_irradiance": float(row["solar_irradiance"]  or 0),
        }
    return {
        "temperature": 0.0, "humidity": 0.0,
        "cloud_cover": 0.0, "wind_speed": 0.0,
        "solar_irradiance": 0.0
    }