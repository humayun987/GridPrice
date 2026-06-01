# import uuid
# import math
# import pandas as pd
# from datetime import datetime, timedelta
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import text


# async def build_features_and_predict(
#     db: AsyncSession,
#     market: str = "GDAM",
#     state: str = "Telangana"
# ) -> dict:
#     """
#     Full pipeline for one state:
#     1. Read historical prices
#     2. Read tomorrow's weather
#     3. Build 96-block feature payload
#     4. Call ML service
#     5. Save predictions to DB
#     """
#     print(f"[Pipeline] Starting for {state} - {market}")

#     try:
#         # ── Step 1: Historical prices ─────────────────────────
#         historical_df = await _fetch_historical_prices(db, state, market)
#         if historical_df.empty:
#             raise ValueError(
#                 f"No historical data for {state}. Run scraper first."
#             )
#         print(f"[Pipeline] Historical rows: {len(historical_df)}")

#         # ── Step 2: Tomorrow's weather ────────────────────────
#         weather_df = await _fetch_tomorrow_weather(db, state)
#         if weather_df.empty:
#             raise ValueError(
#                 f"No weather data for {state}. Run weather fetch first."
#             )
#         print(f"[Pipeline] Weather rows: {len(weather_df)}")

#         # ── Step 3: Build payload ─────────────────────────────
#         payload = _build_payload(historical_df, weather_df, market, state)
#         print(f"[Pipeline] Payload blocks: {len(payload)}")

#         # ── Step 4: Call ML service ───────────────────────────
#         from app.services.ml_service import call_ml_service
#         predictions = await call_ml_service(payload)
#         print(f"[Pipeline] Predictions received: {len(predictions)}")

#         # ── Step 5: Save to DB ────────────────────────────────
#         forecast_run_id = await _save_predictions(
#             db, predictions, market, state
#         )
#         print(f"[Pipeline] Saved run: {forecast_run_id}")

#         return {
#             "status": "success",
#             "forecast_run_id": forecast_run_id,
#             "blocks_predicted": len(predictions),
#             "state": state,
#             "market": market,
#         }

#     except Exception as e:
#         print(f"[Pipeline] Failed for {state}: {e}")
#         return {"status": "failed", "error": str(e), "state": state}


# # ─── Fetch historical prices ──────────────────────────────────────────────────

# async def _fetch_historical_prices(
#     db: AsyncSession,
#     state: str,
#     market: str
# ) -> pd.DataFrame:
#     """
#     Reads last 2 days of MCP data for the state.
#     2 days needed for lag_96 (yesterday same time).
#     """
#     result = await db.execute(
#         text("""
#             SELECT
#                 datetime_block,
#                 mcp_rs_mwh,
#                 cleared_buy_mw,
#                 cleared_sell_mw
#             FROM historical_prices
#             WHERE
#                 region = :state
#                 AND market = :market
#                 AND datetime_block >= NOW() - INTERVAL '2 days'
#             ORDER BY datetime_block ASC
#         """),
#         {"state": state, "market": market}
#     )

#     rows = result.fetchall()
#     if not rows:
#         return pd.DataFrame()

#     df = pd.DataFrame(rows, columns=[
#         "datetime_block", "mcp_rs_mwh",
#         "cleared_buy_mw", "cleared_sell_mw"
#     ])

#     # Strip timezone info for consistent comparison
#     df["datetime_block"] = pd.to_datetime(
#         df["datetime_block"]
#     ).dt.tz_localize(None)

#     df = df.sort_values("datetime_block").reset_index(drop=True)
#     return df


# # ─── Fetch tomorrow's weather ─────────────────────────────────────────────────

# async def _fetch_tomorrow_weather(
#     db: AsyncSession,
#     state: str
# ) -> pd.DataFrame:
#     """
#     Reads tomorrow's 24 hourly weather rows for the state.
#     """
#     tomorrow = datetime.now().date() + timedelta(days=1)
#     tomorrow_start = datetime.combine(tomorrow, datetime.min.time())
#     tomorrow_end   = tomorrow_start + timedelta(days=1)

#     result = await db.execute(
#         text("""
#             SELECT
#                 datetime_hour,
#                 temperature,
#                 humidity,
#                 cloud_cover,
#                 wind_speed,
#                 solar_irradiance
#             FROM raw_weather_forecasts
#             WHERE
#                 region = :state
#                 AND datetime_hour >= :start
#                 AND datetime_hour < :end
#             ORDER BY datetime_hour ASC
#         """),
#         {"state": state, "start": tomorrow_start, "end": tomorrow_end}
#     )

#     rows = result.fetchall()
#     if not rows:
#         return pd.DataFrame()

#     df = pd.DataFrame(rows, columns=[
#         "datetime_hour", "temperature", "humidity",
#         "cloud_cover", "wind_speed", "solar_irradiance"
#     ])

#     # Strip timezone info for consistent comparison
#     df["datetime_hour"] = pd.to_datetime(
#         df["datetime_hour"]
#     ).dt.tz_localize(None)

#     return df


# # ─── Build 96-block payload ───────────────────────────────────────────────────

# def _build_payload(
#     historical_df: pd.DataFrame,
#     weather_df: pd.DataFrame,
#     market: str,
#     state: str
# ) -> list[dict]:
#     """
#     Builds 15 features for each of 96 tomorrow blocks.

#     Weather is hourly (24 rows) — each hour covers 4 blocks:
#       14:00 weather → used for 14:00, 14:15, 14:30, 14:45 blocks
#     """
#     tomorrow = datetime.now().date() + timedelta(days=1)
#     payload = []

#     for block_idx in range(96):
#         minutes    = block_idx * 15
#         block_time = datetime.combine(
#             tomorrow, datetime.min.time()
#         ) + timedelta(minutes=minutes)

#         # ── Lag features ──────────────────────────────────────
#         lag_1  = _get_mcp_at(historical_df, block_time - timedelta(minutes=15))
#         lag_4  = _get_mcp_at(historical_df, block_time - timedelta(hours=1))
#         lag_96 = _get_mcp_at(historical_df, block_time - timedelta(days=1))

#         # ── Rolling features ──────────────────────────────────
#         rolling_window = _get_rolling_window(historical_df, block_time, n=4)
#         rolling_mean_4 = float(rolling_window.mean()) if len(rolling_window) > 0 else lag_1
#         rolling_std_4  = float(rolling_window.std())  if len(rolling_window) > 1 else 0.0

#         # ── Demand supply ratio ───────────────────────────────
#         demand_supply_ratio = _get_demand_supply_ratio(historical_df, block_time)

#         # ── Weather features ──────────────────────────────────
#         # Round block time DOWN to nearest hour to match weather row
#         # e.g. 14:15, 14:30, 14:45 all become 14:00
#         block_hour = block_time.replace(minute=0, second=0, microsecond=0)
#         weather = _get_weather_for_block(weather_df, block_hour)

#         # ── Datetime features ─────────────────────────────────
#         hour        = block_time.hour + block_time.minute / 60.0
#         hour_sin    = math.sin(2 * math.pi * hour / 24)
#         hour_cos    = math.cos(2 * math.pi * hour / 24)
#         day_of_week = block_time.weekday()
#         is_weekend  = 1 if day_of_week >= 5 else 0

#         payload.append({
#             "datetime_block":      block_time.isoformat(),
#             "market":              market,
#             "state":               state,
#             "lag_1":               lag_1,
#             "lag_4":               lag_4,
#             "lag_96":              lag_96,
#             "rolling_mean_4":      round(rolling_mean_4, 4),
#             "rolling_std_4":       round(rolling_std_4, 4),
#             "demand_supply_ratio": demand_supply_ratio,
#             "temperature":         weather.get("temperature", 0.0),
#             "humidity":            weather.get("humidity", 0.0),
#             "cloud_cover":         weather.get("cloud_cover", 0.0),
#             "wind_speed":          weather.get("wind_speed", 0.0),
#             "solar_irradiance":    weather.get("solar_irradiance", 0.0),
#             "hour_sin":            round(hour_sin, 6),
#             "hour_cos":            round(hour_cos, 6),
#             "day_of_week":         day_of_week,
#             "is_weekend":          is_weekend,
#         })

#     return payload


# # ─── Save predictions ─────────────────────────────────────────────────────────

# async def _save_predictions(
#     db: AsyncSession,
#     predictions: list[dict],
#     market: str,
#     state: str
# ) -> str:
#     """
#     Saves 1 forecast_run row and 96 forecast rows.
#     Returns forecast_run_id.
#     """
#     tomorrow        = datetime.now().date() + timedelta(days=1)
#     forecast_run_id = str(uuid.uuid4())

#     # Write forecast_run
#     await db.execute(
#         text("""
#             INSERT INTO forecast_runs
#             (id, market, region, forecast_date,
#              model_run_timestamp, status, created_at)
#             VALUES
#             (:id, :market, :region, :forecast_date,
#              :model_run_timestamp, :status, :created_at)
#         """),
#         {
#             "id":                   forecast_run_id,
#             "market":               market,
#             "region":               state,
#             "forecast_date":        tomorrow,
#             "model_run_timestamp":  datetime.utcnow(),
#             "status":               "completed",
#             "created_at":           datetime.utcnow(),
#         }
#     )

#     # Write 96 forecast rows
#     for pred in predictions:
#         await db.execute(
#             text("""
#                 INSERT INTO forecasts
#                 (id, forecast_run_id, market, region,
#                  datetime_block, predicted_price,
#                  lower_ci, upper_ci, confidence_level, created_at)
#                 VALUES
#                 (:id, :forecast_run_id, :market, :region,
#                  :datetime_block, :predicted_price,
#                  :lower_ci, :upper_ci, :confidence_level, :created_at)
#             """),
#             {
#                 "id":               str(uuid.uuid4()),
#                 "forecast_run_id":  forecast_run_id,
#                 "market":           market,
#                 "region":           state,
#                 "datetime_block":   datetime.fromisoformat(pred["datetime_block"]),
#                 "predicted_price":  pred["predicted_price"],
#                 "lower_ci":         pred["lower_ci"],
#                 "upper_ci":         pred["upper_ci"],
#                 "confidence_level": pred["confidence_level"],
#                 "created_at":       datetime.utcnow(),
#             }
#         )

#     await db.commit()
#     return forecast_run_id


# # ─── Helpers ──────────────────────────────────────────────────────────────────

# def _get_mcp_at(df: pd.DataFrame, target_time: datetime) -> float:
#     """Gets MCP at exact datetime. Returns 0.0 if not found."""
#     match = df[df["datetime_block"] == pd.Timestamp(target_time)]
#     if not match.empty:
#         return float(match.iloc[0]["mcp_rs_mwh"])
#     return 0.0


# def _get_rolling_window(
#     df: pd.DataFrame,
#     block_time: datetime,
#     n: int = 4
# ) -> pd.Series:
#     """Gets last N MCP prices before block_time."""
#     before = df[df["datetime_block"] < pd.Timestamp(block_time)]
#     return before["mcp_rs_mwh"].tail(n)


# def _get_demand_supply_ratio(
#     df: pd.DataFrame,
#     block_time: datetime
# ) -> float:
#     """Gets cleared_buy / cleared_sell from most recent block."""
#     before = df[df["datetime_block"] < pd.Timestamp(block_time)]
#     if before.empty:
#         return 1.0
#     latest = before.iloc[-1]
#     buy  = float(latest["cleared_buy_mw"]  or 0)
#     sell = float(latest["cleared_sell_mw"] or 0)
#     if sell == 0:
#         return 1.0
#     return round(buy / sell, 4)


# def _get_weather_for_block(
#     weather_df: pd.DataFrame,
#     block_hour: datetime      # already rounded to hour
# ) -> dict:
#     """
#     Gets weather for a block by matching exact hour.
#     block_hour must already be rounded down to the hour.
#     4 consecutive blocks share the same weather row.
#     """
#     match = weather_df[
#         weather_df["datetime_hour"] == pd.Timestamp(block_hour)
#     ]
#     if not match.empty:
#         row = match.iloc[0]
#         return {
#             "temperature":      float(row["temperature"]      or 0),
#             "humidity":         float(row["humidity"]          or 0),
#             "cloud_cover":      float(row["cloud_cover"]       or 0),
#             "wind_speed":       float(row["wind_speed"]        or 0),
#             "solar_irradiance": float(row["solar_irradiance"]  or 0),
#         }
#     return {
#         "temperature": 0.0, "humidity": 0.0,
#         "cloud_cover": 0.0, "wind_speed": 0.0,
#         "solar_irradiance": 0.0
#     }

import uuid
import io
import math
import pandas as pd
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def build_features_and_predict(
    db: AsyncSession,
    state: str = "Telangana",
    target_market: str = "GDAM",
) -> dict:
    """
    Full pipeline:
    1. Fetch last 2 days of DAM, GDAM, RTM prices from DB
    2. Compute 16 features for each of tomorrow's 96 blocks
    3. Build 96-row CSV
    4. Send to ML service /api/predict/features
    5. Parse P10/P50/P90 predictions
    6. Save to forecast_runs + forecasts tables
    """
    print(f"[Pipeline] Starting for {state} - {target_market}")

    try:
        today    = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        # Need 2 days back for lag_192 (192 × 15min = 48 hours)
        start_date = today - timedelta(days=2)

        # ── Step 1: Fetch all market prices ───────────────────
        prices = await _fetch_all_market_prices(db, state, start_date)
        if not prices:
            raise ValueError(
                f"No price data for {state}. "
                f"Run scraper for DAM, GDAM, RTM first."
            )

        gdam_df = prices.get("GDAM", pd.DataFrame())
        dam_df  = prices.get("DAM",  pd.DataFrame())
        rtm_df  = prices.get("RTM",  pd.DataFrame())

        print(f"[Pipeline] GDAM rows: {len(gdam_df)}, "
              f"DAM rows: {len(dam_df)}, RTM rows: {len(rtm_df)}")

        # ── Step 2: Build 96-row feature payload ──────────────
        feature_rows = _build_features(
            gdam_df, dam_df, rtm_df, tomorrow
        )
        print(f"[Pipeline] Feature rows built: {len(feature_rows)}")

        if len(feature_rows) != 96:
            raise ValueError(
                f"Expected 96 feature rows, got {len(feature_rows)}"
            )

        # ── Step 3: Build CSV ──────────────────────────────────
        csv_content = _build_csv(feature_rows)
        print(f"[Pipeline] CSV built: 96 rows × 17 columns")

        # ── Step 4: Call ML service ────────────────────────────
        from app.services.ml_service import call_ml_service
        predictions = await call_ml_service(csv_content)
        print(f"[Pipeline] Predictions received: {len(predictions)}")

        # ── Step 5: Save predictions ───────────────────────────
        forecast_run_id = await _save_predictions(
            db, predictions, target_market, state, tomorrow
        )
        print(f"[Pipeline] Saved run: {forecast_run_id}")

        return {
            "status":           "success",
            "forecast_run_id":  forecast_run_id,
            "blocks_predicted": len(predictions),
            "state":            state,
            "market":           target_market,
        }

    except Exception as e:
        print(f"[Pipeline] Failed for {state}: {e}")
        return {"status": "failed", "error": str(e), "state": state}


# ─── Fetch all market prices ──────────────────────────────────────────────────

async def _fetch_all_market_prices(
    db: AsyncSession,
    state: str,
    start_date: date,
) -> dict[str, pd.DataFrame]:
    """
    Fetches DAM, GDAM, RTM prices separately.
    Returns dict of {market_name: DataFrame}.
    Each DataFrame sorted by datetime_block ASC.
    """
    result = await db.execute(
        text("""
            SELECT
                datetime_block,
                market,
                mcp_rs_mwh
            FROM historical_prices
            WHERE
                region = :state
                AND datetime_block >= :start
            ORDER BY market, datetime_block ASC
        """),
        {
            "state": state,
            "start": datetime.combine(start_date, datetime.min.time()),
        }
    )

    rows = result.fetchall()
    if not rows:
        return {}

    df = pd.DataFrame(rows, columns=["datetime_block", "market", "mcp_rs_mwh"])
    df["datetime_block"] = pd.to_datetime(
        df["datetime_block"]
    ).dt.tz_localize(None)
    df = df.sort_values("datetime_block").reset_index(drop=True)

    # Split by market
    result_dict = {}
    for market in ["GDAM", "DAM", "RTM"]:
        market_df = df[df["market"] == market][
            ["datetime_block", "mcp_rs_mwh"]
        ].copy().reset_index(drop=True)
        result_dict[market] = market_df

    return result_dict


# ─── Build 96 feature rows ────────────────────────────────────────────────────

def _build_features(
    gdam_df: pd.DataFrame,
    dam_df: pd.DataFrame,
    rtm_df: pd.DataFrame,
    tomorrow: date,
) -> list[dict]:
    """
    Computes all 16 features for each of 96 tomorrow blocks.

    Feature definitions:
      price_lag_96   = GDAM MCP at (block_time - 96 steps = 24h back = today same time)
      price_lag_192  = GDAM MCP at (block_time - 192 steps = 48h back = yesterday same time)
      GDAM_MCP_lag_4 = GDAM MCP at (block_time - 4 steps = 1 hour back)
      DAM_MCP_lag_1  = DAM MCP at (block_time - 1 step = 15 min back)
      DAM_MCP_lag_4  = DAM MCP at (block_time - 4 steps = 1 hour back)
      DAM_MCP_lag_96 = DAM MCP at (block_time - 96 steps = 24h back)
      RTM_MCP_lag_1  = RTM MCP at (block_time - 1 step)
      RTM_MCP_lag_4  = RTM MCP at (block_time - 4 steps)
      RTM_MCP_lag_96 = RTM MCP at (block_time - 96 steps)
      DAM_GDAM_spread  = DAM_lag_96 - GDAM_lag_96 (same lag time)
      RTM_DAM_spread   = RTM_lag_96 - DAM_lag_96
      RTM_GDAM_spread  = RTM_lag_96 - GDAM_lag_96
      hour           = integer hour of block (0-23)
      hour_sin       = sin(2π × hour / 24)
      hour_cos       = cos(2π × hour / 24)
      weekday        = 0=Monday ... 6=Sunday
    """
    rows = []

    for block_idx in range(96):
        block_time = datetime.combine(
            tomorrow, datetime.min.time()
        ) + timedelta(minutes=block_idx * 15)

        # ── GDAM lags ─────────────────────────────────────────
        price_lag_96  = _get_price_at(gdam_df, block_time - timedelta(days=1))
        price_lag_192 = _get_price_at(gdam_df, block_time - timedelta(days=2))
        gdam_lag_4    = _get_price_at(gdam_df, block_time - timedelta(hours=1))

        # ── DAM lags ──────────────────────────────────────────
        dam_lag_1  = _get_price_at(dam_df, block_time - timedelta(minutes=15))
        dam_lag_4  = _get_price_at(dam_df, block_time - timedelta(hours=1))
        dam_lag_96 = _get_price_at(dam_df, block_time - timedelta(days=1))

        # ── RTM lags ──────────────────────────────────────────
        rtm_lag_1  = _get_price_at(rtm_df, block_time - timedelta(minutes=15))
        rtm_lag_4  = _get_price_at(rtm_df, block_time - timedelta(hours=1))
        rtm_lag_96 = _get_price_at(rtm_df, block_time - timedelta(days=1))

        # ── Spreads (using lag_96 values — same time yesterday) ─
        dam_gdam_spread = round(dam_lag_96  - price_lag_96, 4)
        rtm_dam_spread  = round(rtm_lag_96  - dam_lag_96,   4)
        rtm_gdam_spread = round(rtm_lag_96  - price_lag_96, 4)

        # ── Datetime features ─────────────────────────────────
        hour        = block_time.hour
        hour_sin    = round(math.sin(2 * math.pi * hour / 24), 6)
        hour_cos    = round(math.cos(2 * math.pi * hour / 24), 6)
        weekday     = block_time.weekday()   # 0=Monday, 6=Sunday

        rows.append({
            "datetime":       block_time.strftime("%Y-%m-%d %H:%M:%S"),
            "DAM_GDAM_spread":  dam_gdam_spread,
            "DAM_MCP_lag_1":    dam_lag_1,
            "DAM_MCP_lag_4":    dam_lag_4,
            "DAM_MCP_lag_96":   dam_lag_96,
            "GDAM_MCP_lag_4":   gdam_lag_4,
            "RTM_DAM_spread":   rtm_dam_spread,
            "RTM_GDAM_spread":  rtm_gdam_spread,
            "RTM_MCP_lag_1":    rtm_lag_1,
            "RTM_MCP_lag_4":    rtm_lag_4,
            "RTM_MCP_lag_96":   rtm_lag_96,
            "hour":             hour,
            "hour_cos":         hour_cos,
            "hour_sin":         hour_sin,
            "price_lag_192":    price_lag_192,
            "price_lag_96":     price_lag_96,
            "weekday":          weekday,
        })

    return rows


# ─── Build CSV ────────────────────────────────────────────────────────────────

def _build_csv(feature_rows: list[dict]) -> str:
    """
    Converts feature rows to CSV string.
    Column order matches exactly what ML service expects.
    """
    df = pd.DataFrame(feature_rows)

    # Exact column order required by ML service
    columns = [
        "datetime",
        "DAM_GDAM_spread",
        "DAM_MCP_lag_1",
        "DAM_MCP_lag_4",
        "DAM_MCP_lag_96",
        "GDAM_MCP_lag_4",
        "RTM_DAM_spread",
        "RTM_GDAM_spread",
        "RTM_MCP_lag_1",
        "RTM_MCP_lag_4",
        "RTM_MCP_lag_96",
        "hour",
        "hour_cos",
        "hour_sin",
        "price_lag_192",
        "price_lag_96",
        "weekday",
    ]

    return df[columns].to_csv(index=False)


# ─── Save predictions ─────────────────────────────────────────────────────────

async def _save_predictions(
    db: AsyncSession,
    predictions: list[dict],
    market: str,
    state: str,
    forecast_date: date,
) -> str:
    """
    Saves 1 forecast_run row and up to 96 forecast rows.
    Returns forecast_run_id.
    """
    forecast_run_id = str(uuid.uuid4())

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
            "id":                  forecast_run_id,
            "market":              market,
            "region":              state,
            "forecast_date":       forecast_date,
            "model_run_timestamp": datetime.utcnow(),
            "status":              "completed",
            "created_at":          datetime.utcnow(),
        }
    )

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
                "datetime_block":   pred["datetime_block"],
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

def _get_price_at(df: pd.DataFrame, target_time: datetime) -> float:
    """
    Gets MCP price at exact datetime from a market DataFrame.
    Returns 0.0 if not found — meaning data missing for that block.
    """
    if df.empty:
        return 0.0
    match = df[df["datetime_block"] == pd.Timestamp(target_time)]
    if not match.empty:
        return round(float(match.iloc[0]["mcp_rs_mwh"]), 4)
    return 0.0