# import uuid
# import io
# import math
# import pandas as pd
# from datetime import datetime, timedelta, date
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import text


# async def build_features_and_predict(
#     db: AsyncSession,
#     state: str = "Telangana",
#     target_market: str = "GDAM",
# ) -> dict:
#     """
#     Full pipeline:
#     1. Fetch last 3 days of DAM, GDAM, RTM prices from DB
#        (3 days needed: today for lag_96, yesterday for lag_192,
#         day before for any edge cases)
#     2. Compute 16 features for each of tomorrow's 96 blocks
#     3. Build 96-row CSV
#     4. Send to ML service /api/predict/features
#     5. Parse P10/P50/P90 predictions
#     6. Save to forecast_runs + forecasts tables
#     """
#     print(f"[Pipeline] Starting for {state} - {target_market}")

#     try:
#         today    = datetime.now().date()
#         tomorrow = today + timedelta(days=1)

#         # 3 days back ensures we have:
#         # - today's full data (for lag_96 and DAM/GDAM lag_1, lag_4)
#         # - yesterday's full data (for lag_192)
#         # - day before yesterday (buffer for edge blocks near midnight)
#         start_date = today - timedelta(days=3)

#         # ── Step 1: Fetch all market prices ───────────────────
#         prices = await _fetch_all_market_prices(db, state, start_date)
#         if not prices:
#             raise ValueError(
#                 f"No price data for {state}. "
#                 f"Run scraper for DAM, GDAM, RTM first."
#             )

#         gdam_df = prices.get("GDAM", pd.DataFrame())
#         dam_df  = prices.get("DAM",  pd.DataFrame())
#         rtm_df  = prices.get("RTM",  pd.DataFrame())

#         print(
#             f"[Pipeline] GDAM rows: {len(gdam_df)}, "
#             f"DAM rows: {len(dam_df)}, RTM rows: {len(rtm_df)}"
#         )

#         # ── Step 2: Build 96-row feature payload ──────────────
#         feature_rows = _build_features(gdam_df, dam_df, rtm_df, today, tomorrow)
#         print(f"[Pipeline] Feature rows built: {len(feature_rows)}")

#         if len(feature_rows) != 96:
#             raise ValueError(
#                 f"Expected 96 feature rows, got {len(feature_rows)}"
#             )

#         # ── Step 3: Build CSV ──────────────────────────────────
#         csv_content = _build_csv(feature_rows)
#         print(f"[Pipeline] CSV built: 96 rows × 17 columns")

#         # ── Step 4: Call ML service ────────────────────────────
#         from app.services.ml_service import call_ml_service
#         predictions = await call_ml_service(csv_content)
#         print(f"[Pipeline] Predictions received: {len(predictions)}")

#         # ── Step 5: Save predictions ───────────────────────────
#         forecast_run_id = await _save_predictions(
#             db, predictions, target_market, state, tomorrow
#         )
#         print(f"[Pipeline] Saved run: {forecast_run_id}")

#         return {
#             "status":           "success",
#             "forecast_run_id":  forecast_run_id,
#             "blocks_predicted": len(predictions),
#             "state":            state,
#             "market":           target_market,
#         }

#     except Exception as e:
#         print(f"[Pipeline] Failed for {state}: {e}")
#         return {"status": "failed", "error": str(e), "state": state}


# # ─── Fetch all market prices ──────────────────────────────────────────────────
# async def _fetch_all_market_prices(
#     db: AsyncSession,
#     state: str,
#     start_date: date,
# ) -> dict[str, pd.DataFrame]:
#     """
#     Fetches DAM, GDAM, RTM prices for the given state.
#     Pulls from start_date onwards to cover 3 days of history.
#     Returns dict of {market_name: DataFrame} sorted by datetime_block ASC.
#     """
#     result = await db.execute(
#         text("""
#             SELECT
#                 datetime_block,
#                 market,
#                 mcp_rs_mwh
#             FROM historical_prices
#             WHERE
#                 region = :state
#                 AND datetime_block >= :start
#             ORDER BY market, datetime_block ASC
#         """),
#         {
#             "state": state,
#             "start": datetime.combine(start_date, datetime.min.time()),
#         }
#     )

#     rows = result.fetchall()
#     if not rows:
#         return {}

#     df = pd.DataFrame(rows, columns=["datetime_block", "market", "mcp_rs_mwh"])

#     # Strip timezone for consistent comparison
#     df["datetime_block"] = pd.to_datetime(
#         df["datetime_block"]
#     ).dt.tz_localize(None)

#     df = df.sort_values("datetime_block").reset_index(drop=True)

#     # Split into per-market DataFrames
#     result_dict = {}
#     for market in ["GDAM", "DAM", "RTM"]:
#         market_df = df[df["market"] == market][
#             ["datetime_block", "mcp_rs_mwh"]
#         ].copy().reset_index(drop=True)
#         result_dict[market] = market_df

#     return result_dict


# # ─── Build 96 feature rows ────────────────────────────────────────────────────

# def _build_features(
#     gdam_df: pd.DataFrame,
#     dam_df: pd.DataFrame,
#     rtm_df: pd.DataFrame,
#     today: date,
#     tomorrow: date,
# ) -> list[dict]:
#     """
#     Builds 16 features for each of tomorrow's 96 blocks.

#     KEY INSIGHT: All lag lookups are relative to TODAY's equivalent block,
#     not tomorrow's block_time directly. Tomorrow's prices don't exist yet.

#     For each tomorrow block at position i (0..95):
#       today_block    = today 00:00 + i*15min  ← today's equivalent block
#       yesterday_block= yesterday 00:00 + i*15min

#       Lags are then offsets FROM today_block:
#         price_lag_96   = GDAM[today_block]          (today same time, 96 steps back from tomorrow)
#         price_lag_192  = GDAM[yesterday_block]       (2 days back from tomorrow)
#         GDAM_MCP_lag_4 = GDAM[today_block - 1hr]    (4 steps back from tomorrow = today same time - 1hr)
#         DAM_MCP_lag_1  = DAM[today_block - 15min]   (1 step back)
#         DAM_MCP_lag_4  = DAM[today_block - 1hr]     (4 steps back)
#         DAM_MCP_lag_96 = DAM[today_block]           (96 steps back = today same time)
#         RTM_MCP_lag_1  = RTM[today_block - 15min]   (may be None if not scraped yet)
#         RTM_MCP_lag_4  = RTM[today_block - 1hr]     (may be None)
#         RTM_MCP_lag_96 = RTM[today_block]           (may be None)

#       Spreads use today's actual prices (all use today_block reference):
#         DAM_GDAM_spread = DAM[today_block] - GDAM[today_block]
#         RTM_DAM_spread  = RTM[today_block] - DAM[today_block]   (None if RTM unavailable)
#         RTM_GDAM_spread = RTM[today_block] - GDAM[today_block]  (None if RTM unavailable)

#       Calendar features from tomorrow's block datetime:
#         hour, hour_sin, hour_cos, weekday
#     """
#     rows = []

#     for block_idx in range(96):
#         minutes = block_idx * 15

#         # Tomorrow's block datetime (used only for calendar features)
#         tomorrow_block = datetime.combine(
#             tomorrow, datetime.min.time()
#         ) + timedelta(minutes=minutes)

#         # Today's equivalent block (used for all price lookups)
#         today_block = datetime.combine(
#             today, datetime.min.time()
#         ) + timedelta(minutes=minutes)

#         # Yesterday's equivalent block
#         yesterday_block = datetime.combine(
#             today - timedelta(days=1), datetime.min.time()
#         ) + timedelta(minutes=minutes)

#         # ── GDAM features ─────────────────────────────────────
#         # price_lag_96: GDAM at today's same block (96 steps before tomorrow)
#         price_lag_96 = _get_price_at(gdam_df, today_block)

#         # price_lag_192: GDAM at yesterday's same block (192 steps before tomorrow)
#         price_lag_192 = _get_price_at(gdam_df, yesterday_block)

#         # GDAM_MCP_lag_4: GDAM 4 steps (1 hour) before today's block
#         gdam_lag_4 = _get_price_at(gdam_df, today_block - timedelta(hours=1))

#         # ── DAM features ──────────────────────────────────────
#         # DAM_MCP_lag_1: DAM 1 step (15 min) before today's block
#         dam_lag_1 = _get_price_at(dam_df, today_block - timedelta(minutes=15))

#         # DAM_MCP_lag_4: DAM 4 steps (1 hour) before today's block
#         dam_lag_4 = _get_price_at(dam_df, today_block - timedelta(hours=1))

#         # DAM_MCP_lag_96: DAM at today's same block (96 steps before tomorrow)
#         dam_lag_96 = _get_price_at(dam_df, yesterday_block)

#         # ── RTM features ──────────────────────────────────────
#         # RTM_MCP_lag_1: RTM 1 step before today's block (None if not scraped)
#         rtm_lag_1 = _get_price_at(rtm_df, today_block - timedelta(minutes=15))

#         # RTM_MCP_lag_4: RTM 4 steps before today's block (None if not scraped)
#         rtm_lag_4 = _get_price_at(rtm_df, today_block - timedelta(hours=1))

#         # RTM_MCP_lag_96: RTM at today's same block (None if not scraped)
#         rtm_lag_96 = _get_price_at(rtm_df, yesterday_block)

#         # ── Spreads — use today's prices ──────────────────────
#         # DAM and GDAM fully available today → always computable
#         # RTM → None if today's block not yet scraped → spread also None
#         dam_gdam_spread = (
#             round(dam_lag_96 - price_lag_96, 4)
#             if dam_lag_96 is not None and price_lag_96 is not None
#             else None
#         )

#         rtm_dam_spread = (
#             round(rtm_lag_96 - dam_lag_96, 4)
#             if rtm_lag_96 is not None and dam_lag_96 is not None
#             else None
#         )

#         rtm_gdam_spread = (
#             round(rtm_lag_96 - price_lag_96, 4)
#             if rtm_lag_96 is not None and price_lag_96 is not None
#             else None
#         )

#         # ── Calendar features from tomorrow's block ───────────
#         hour     = tomorrow_block.hour
#         hour_sin = round(math.sin(2 * math.pi * hour / 24), 6)
#         hour_cos = round(math.cos(2 * math.pi * hour / 24), 6)
#         weekday  = tomorrow_block.weekday()   # 0=Monday, 6=Sunday

#         rows.append({
#             "datetime":        tomorrow_block.strftime("%Y-%m-%d %H:%M:%S"),
#             "DAM_GDAM_spread": dam_gdam_spread,
#             "DAM_MCP_lag_1":   dam_lag_1,
#             "DAM_MCP_lag_4":   dam_lag_4,
#             "DAM_MCP_lag_96":  dam_lag_96,
#             "GDAM_MCP_lag_4":  gdam_lag_4,
#             "RTM_DAM_spread":  rtm_dam_spread,
#             "RTM_GDAM_spread": rtm_gdam_spread,
#             "RTM_MCP_lag_1":   rtm_lag_1,
#             "RTM_MCP_lag_4":   rtm_lag_4,
#             "RTM_MCP_lag_96":  rtm_lag_96,
#             "hour":            hour,
#             "hour_cos":        hour_cos,
#             "hour_sin":        hour_sin,
#             "price_lag_192":   price_lag_192,
#             "price_lag_96":    price_lag_96,
#             "weekday":         weekday,
#         })

#     return rows


# # ─── Build CSV ────────────────────────────────────────────────────────────────

# def _build_csv(feature_rows: list[dict]) -> str:
#     """
#     Converts 96 feature rows into CSV string.
#     Column order matches exactly what /api/predict/features expects.
#     None values become NaN in the CSV — ML model handles them correctly.
#     """
#     df = pd.DataFrame(feature_rows)

#     columns = [
#         "datetime",
#         "DAM_GDAM_spread",
#         "DAM_MCP_lag_1",
#         "DAM_MCP_lag_4",
#         "DAM_MCP_lag_96",
#         "GDAM_MCP_lag_4",
#         "RTM_DAM_spread",
#         "RTM_GDAM_spread",
#         "RTM_MCP_lag_1",
#         "RTM_MCP_lag_4",
#         "RTM_MCP_lag_96",
#         "hour",
#         "hour_cos",
#         "hour_sin",
#         "price_lag_192",
#         "price_lag_96",
#         "weekday",
#     ]

#     # None values automatically become NaN in pandas → written as empty in CSV
#     return df[columns].to_csv(index=False)


# # ─── Save predictions ─────────────────────────────────────────────────────────

# async def _save_predictions(
#     db: AsyncSession,
#     predictions: list[dict],
#     market: str,
#     state: str,
#     forecast_date: date,
# ) -> str:
#     """
#     Saves 1 forecast_run row and 96 forecast rows.
#     Returns forecast_run_id.
#     """
#     forecast_run_id = str(uuid.uuid4())

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
#             "id":                  forecast_run_id,
#             "market":              market,
#             "region":              state,
#             "forecast_date":       forecast_date,
#             "model_run_timestamp": datetime.utcnow(),
#             "status":              "completed",
#             "created_at":          datetime.utcnow(),
#         }
#     )

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
#                 "datetime_block":   pred["datetime_block"],
#                 "predicted_price":  pred["predicted_price"],
#                 "lower_ci":         pred["lower_ci"],
#                 "upper_ci":         pred["upper_ci"],
#                 "confidence_level": pred["confidence_level"],
#                 "created_at":       datetime.utcnow(),
#             }
#         )

#     await db.commit()
#     return forecast_run_id


# # ─── Helper ───────────────────────────────────────────────────────────────────

# def _get_price_at(df: pd.DataFrame, target_time: datetime) -> float | None:
#     """
#     Gets MCP price at exact datetime from a market DataFrame.
#     Returns None if not found.

#     None → pandas writes NaN in CSV → ML model handles correctly.
#     This is correct behaviour for RTM blocks not yet scraped.
#     DAM and GDAM should always return a value since full day is available.
#     """
#     if df.empty:
#         return None
#     match = df[df["datetime_block"] == pd.Timestamp(target_time)]
#     if not match.empty:
#         return round(float(match.iloc[0]["mcp_rs_mwh"]), 4)
#     return None

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
    1. Fetch last 3 days of DAM, GDAM, RTM prices from DB
    2. Dispatch to the correct per-market feature builder
    3. Build 96-row CSV
    4. Send to the correct ML service
    5. Parse P10/P50/P90 predictions
    6. Save to forecast_runs + forecasts tables
    """
    print(f"[Pipeline] Starting for {state} - {target_market}")

    try:
        today    = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        # 3 days back ensures:
        # - today's full data  (lag_96, DAM/GDAM lag_1/lag_4)
        # - yesterday's full data (lag_192)
        # - day before yesterday (buffer for edge blocks near midnight)
        start_date = today - timedelta(days=3)

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

        print(
            f"[Pipeline] GDAM rows: {len(gdam_df)}, "
            f"DAM rows: {len(dam_df)}, RTM rows: {len(rtm_df)}"
        )

        # ── Step 2: Dispatch to correct feature builder ───────
        if target_market == "GDAM":
            feature_rows = _build_features_gdam(gdam_df, dam_df, rtm_df, today, tomorrow)
        elif target_market == "DAM":
            feature_rows = _build_features_dam(gdam_df, dam_df, rtm_df, today, tomorrow)
        elif target_market == "RTM":
            feature_rows = _build_features_rtm(gdam_df, dam_df, rtm_df, today, tomorrow)
        else:
            raise ValueError(f"Unknown market: {target_market}")

        print(f"[Pipeline] Feature rows built: {len(feature_rows)}")

        if len(feature_rows) != 96:
            raise ValueError(
                f"Expected 96 feature rows, got {len(feature_rows)}"
            )

        # ── Step 3: Build CSV ──────────────────────────────────
        csv_content = _build_csv(feature_rows)
        print(f"[Pipeline] CSV built: 96 rows")

        # ── Step 4: Call correct ML service ───────────────────
        from app.services.ml_service import call_ml_service
        predictions = await call_ml_service(csv_content, market=target_market)
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
        print(f"[Pipeline] Failed for {state} - {target_market}: {e}")
        return {"status": "failed", "error": str(e), "state": state, "market": target_market}


# ─── Fetch all market prices ──────────────────────────────────────────────────

async def _fetch_all_market_prices(
    db: AsyncSession,
    state: str,
    start_date: date,
) -> dict[str, pd.DataFrame]:
    """
    Fetches DAM, GDAM, RTM prices for the given state from start_date onwards.
    Returns dict of {market_name: DataFrame} sorted by datetime_block ASC.
    All three markets are always fetched — each builder picks what it needs.
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

    # Strip timezone for consistent comparison
    df["datetime_block"] = pd.to_datetime(
        df["datetime_block"]
    ).dt.tz_localize(None)

    df = df.sort_values("datetime_block").reset_index(drop=True)

    result_dict = {}
    for market in ["GDAM", "DAM", "RTM"]:
        market_df = df[df["market"] == market][
            ["datetime_block", "mcp_rs_mwh"]
        ].copy().reset_index(drop=True)
        result_dict[market] = market_df

    return result_dict


# ─── GDAM feature builder ─────────────────────────────────────────────────────

def _build_features_gdam(
    gdam_df: pd.DataFrame,
    dam_df: pd.DataFrame,
    rtm_df: pd.DataFrame,
    today: date,
    tomorrow: date,
) -> list[dict]:
    """
    Builds 16 features for each of tomorrow's 96 blocks for the GDAM model.

    Lag reference point is today's equivalent block for all lookups.

    Features:
        price_lag_96        = GDAM[today_block]            (96 steps before tomorrow)
        price_lag_192       = GDAM[yesterday_block]        (192 steps before tomorrow)
        GDAM_MCP_lag_4      = GDAM[today_block - 1hr]
        DAM_MCP_lag_1       = DAM[today_block - 15min]
        DAM_MCP_lag_4       = DAM[today_block - 1hr]
        DAM_MCP_lag_96      = DAM[yesterday_block]
        RTM_MCP_lag_1       = RTM[today_block - 15min]
        RTM_MCP_lag_4       = RTM[today_block - 1hr]
        RTM_MCP_lag_96      = RTM[yesterday_block]
        DAM_GDAM_spread     = DAM[today_block] - GDAM[today_block]
        RTM_DAM_spread      = RTM[today_block] - DAM[today_block]
        RTM_GDAM_spread     = RTM[today_block] - GDAM[today_block]
        hour, hour_sin, hour_cos, weekday  (from tomorrow's block)
    """
    rows = []

    for block_idx in range(96):
        minutes = block_idx * 15

        tomorrow_block  = datetime.combine(tomorrow, datetime.min.time()) + timedelta(minutes=minutes)
        today_block     = datetime.combine(today, datetime.min.time()) + timedelta(minutes=minutes)
        yesterday_block = datetime.combine(today - timedelta(days=1), datetime.min.time()) + timedelta(minutes=minutes)

        # ── GDAM lags ─────────────────────────────────────────
        price_lag_96  = _get_price_at(gdam_df, today_block)
        price_lag_192 = _get_price_at(gdam_df, yesterday_block)
        gdam_lag_4    = _get_price_at(gdam_df, today_block - timedelta(hours=1))

        # ── DAM lags ──────────────────────────────────────────
        dam_lag_1  = _get_price_at(dam_df, today_block - timedelta(minutes=15))
        dam_lag_4  = _get_price_at(dam_df, today_block - timedelta(hours=1))
        dam_lag_96 = _get_price_at(dam_df, yesterday_block)

        # ── RTM lags ──────────────────────────────────────────
        rtm_lag_1  = _get_price_at(rtm_df, today_block - timedelta(minutes=15))
        rtm_lag_4  = _get_price_at(rtm_df, today_block - timedelta(hours=1))
        rtm_lag_96 = _get_price_at(rtm_df, yesterday_block)

        # ── Spreads — use today's prices ──────────────────────
        # DAM and GDAM use today_block reference (same as lag_96 lookups)
        # RTM → None if not yet scraped → spread also None
        dam_today  = _get_price_at(dam_df,  today_block)
        gdam_today = _get_price_at(gdam_df, today_block)
        rtm_today  = _get_price_at(rtm_df,  today_block)

        dam_gdam_spread = (
            round(dam_today - gdam_today, 4)
            if dam_today is not None and gdam_today is not None
            else None
        )
        rtm_dam_spread = (
            round(rtm_today - dam_today, 4)
            if rtm_today is not None and dam_today is not None
            else None
        )
        rtm_gdam_spread = (
            round(rtm_today - gdam_today, 4)
            if rtm_today is not None and gdam_today is not None
            else None
        )

        # ── Calendar features from tomorrow's block ───────────
        hour     = tomorrow_block.hour
        hour_sin = round(math.sin(2 * math.pi * hour / 24), 6)
        hour_cos = round(math.cos(2 * math.pi * hour / 24), 6)
        weekday  = tomorrow_block.weekday()

        rows.append({
            "datetime":        tomorrow_block.strftime("%Y-%m-%d %H:%M:%S"),
            "DAM_GDAM_spread": dam_gdam_spread,
            "DAM_MCP_lag_1":   dam_lag_1,
            "DAM_MCP_lag_4":   dam_lag_4,
            "DAM_MCP_lag_96":  dam_lag_96,
            "GDAM_MCP_lag_4":  gdam_lag_4,
            "RTM_DAM_spread":  rtm_dam_spread,
            "RTM_GDAM_spread": rtm_gdam_spread,
            "RTM_MCP_lag_1":   rtm_lag_1,
            "RTM_MCP_lag_4":   rtm_lag_4,
            "RTM_MCP_lag_96":  rtm_lag_96,
            "hour":            hour,
            "hour_cos":        hour_cos,
            "hour_sin":        hour_sin,
            "price_lag_192":   price_lag_192,
            "price_lag_96":    price_lag_96,
            "weekday":         weekday,
        })

    return rows


# ─── DAM feature builder ──────────────────────────────────────────────────────

def _build_features_dam(
    gdam_df: pd.DataFrame,
    dam_df: pd.DataFrame,
    rtm_df: pd.DataFrame,
    today: date,
    tomorrow: date,
) -> list[dict]:
    """
    Builds 15 features for each of tomorrow's 96 blocks for the DAM model.

    Lag reference point is today's equivalent block for all lookups.

    Features:
        price_lag_96        = DAM[today_block]             (96 steps before tomorrow)
        price_lag_192       = DAM[yesterday_block]         (192 steps before tomorrow)
        DAM_MCP_lag_4       = DAM[today_block - 1hr]
        GDAM_MCP_lag_1      = GDAM[today_block - 15min]
        GDAM_MCP_lag_4      = GDAM[today_block - 1hr]
        GDAM_MCP_lag_96     = GDAM[yesterday_block]
        RTM_MCP_lag_1       = RTM[today_block - 15min]
        RTM_MCP_lag_4       = RTM[today_block - 1hr]
        RTM_MCP_lag_96      = RTM[yesterday_block]
        DAM_GDAM_spread     = DAM[today_block] - GDAM[today_block]
        RTM_DAM_spread      = RTM[today_block] - DAM[today_block]
        hour, hour_sin, hour_cos, weekday  (from tomorrow's block)

    Note: price_lag_96 and price_lag_192 are DAM's own prices here,
    unlike GDAM builder where they refer to GDAM prices.
    """
    rows = []

    for block_idx in range(96):
        minutes = block_idx * 15

        tomorrow_block  = datetime.combine(tomorrow, datetime.min.time()) + timedelta(minutes=minutes)
        today_block     = datetime.combine(today, datetime.min.time()) + timedelta(minutes=minutes)
        yesterday_block = datetime.combine(today - timedelta(days=1), datetime.min.time()) + timedelta(minutes=minutes)

        # ── DAM lags ──────────────────────────────────────────
        # price_lag_96/192 refer to DAM's own prices for the DAM model
        price_lag_96  = _get_price_at(dam_df, today_block)
        price_lag_192 = _get_price_at(dam_df, yesterday_block)
        dam_lag_4     = _get_price_at(dam_df, today_block - timedelta(hours=1))

        # ── GDAM lags ─────────────────────────────────────────
        gdam_lag_1  = _get_price_at(gdam_df, today_block - timedelta(minutes=15))
        gdam_lag_4  = _get_price_at(gdam_df, today_block - timedelta(hours=1))
        gdam_lag_96 = _get_price_at(gdam_df, yesterday_block)

        # ── RTM lags ──────────────────────────────────────────
        rtm_lag_1  = _get_price_at(rtm_df, today_block - timedelta(minutes=15))
        rtm_lag_4  = _get_price_at(rtm_df, today_block - timedelta(hours=1))
        rtm_lag_96 = _get_price_at(rtm_df, yesterday_block)

        # ── Spreads — use today's prices ──────────────────────
        dam_today  = _get_price_at(dam_df,  today_block)
        gdam_today = _get_price_at(gdam_df, today_block)
        rtm_today  = _get_price_at(rtm_df,  today_block)

        dam_gdam_spread = (
            round(dam_today - gdam_today, 4)
            if dam_today is not None and gdam_today is not None
            else None
        )
        rtm_dam_spread = (
            round(rtm_today - dam_today, 4)
            if rtm_today is not None and dam_today is not None
            else None
        )

        # ── Calendar features from tomorrow's block ───────────
        hour     = tomorrow_block.hour
        hour_sin = round(math.sin(2 * math.pi * hour / 24), 6)
        hour_cos = round(math.cos(2 * math.pi * hour / 24), 6)
        weekday  = tomorrow_block.weekday()

        rows.append({
            "datetime":        tomorrow_block.strftime("%Y-%m-%d %H:%M:%S"),
            "price_lag_192":   price_lag_192,
            "price_lag_96":    price_lag_96,
            "weekday":         weekday,
            "DAM_MCP_lag_4":   dam_lag_4,
            "hour_sin":        hour_sin,
            "hour":            hour,
            "hour_cos":        hour_cos,
            "GDAM_MCP_lag_1":  gdam_lag_1,
            "GDAM_MCP_lag_4":  gdam_lag_4,
            "GDAM_MCP_lag_96": gdam_lag_96,
            "RTM_MCP_lag_1":   rtm_lag_1,
            "RTM_MCP_lag_4":   rtm_lag_4,
            "RTM_MCP_lag_96":  rtm_lag_96,
            "DAM_GDAM_spread": dam_gdam_spread,
            "RTM_DAM_spread":  rtm_dam_spread,
        })

    return rows


# ─── RTM feature builder (stub) ───────────────────────────────────────────────

def _build_features_rtm(
    gdam_df: pd.DataFrame,
    dam_df: pd.DataFrame,
    rtm_df: pd.DataFrame,
    today: date,
    tomorrow: date,
) -> list[dict]:
    """
    RTM feature builder — STUB.

    TODO (ML team): Replace dummy features with actual RTM model feature spec.
    Current behaviour: returns a minimal dummy payload so the mock ML service
    can generate predictions without crashing. The mock uses price_lag_96
    as base price, which is computed here from RTM's own prices.

    When RTM ML service is ready:
    1. Get feature list from ML team (same format as DAM/GDAM feature_list JSON)
    2. Implement actual feature computation below
    3. Update ML_SERVICE_URL_RTM in .env to point to real service
    """
    rows = []

    for block_idx in range(96):
        minutes = block_idx * 15

        tomorrow_block  = datetime.combine(tomorrow, datetime.min.time()) + timedelta(minutes=minutes)
        today_block     = datetime.combine(today, datetime.min.time()) + timedelta(minutes=minutes)
        yesterday_block = datetime.combine(today - timedelta(days=1), datetime.min.time()) + timedelta(minutes=minutes)

        # Minimal features — enough for mock predict to use price_lag_96 as base
        price_lag_96  = _get_price_at(rtm_df, today_block)
        price_lag_192 = _get_price_at(rtm_df, yesterday_block)

        hour     = tomorrow_block.hour
        hour_sin = round(math.sin(2 * math.pi * hour / 24), 6)
        hour_cos = round(math.cos(2 * math.pi * hour / 24), 6)
        weekday  = tomorrow_block.weekday()

        # Dummy row — column names don't matter for mock service
        rows.append({
            "datetime":      tomorrow_block.strftime("%Y-%m-%d %H:%M:%S"),
            "price_lag_96":  price_lag_96,
            "price_lag_192": price_lag_192,
            "hour":          hour,
            "hour_sin":      hour_sin,
            "hour_cos":      hour_cos,
            "weekday":       weekday,
        })

    return rows


# ─── CSV builder ──────────────────────────────────────────────────────────────

def _build_csv(feature_rows: list[dict]) -> str:
    """
    Converts feature rows into CSV string.
    Column order is preserved from the dict key order —
    each builder defines its own column order matching its model's expectation.
    None values become NaN in pandas → written as empty in CSV.
    ML models handle missing values correctly.
    """
    df = pd.DataFrame(feature_rows)
    columns = list(feature_rows[0].keys())
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
    Saves 1 forecast_run row and 96 forecast rows.
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


# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_price_at(df: pd.DataFrame, target_time: datetime) -> float | None:
    """
    Gets MCP price at exact datetime from a market DataFrame.
    Returns None if not found.
    None → pandas writes NaN in CSV → ML model handles correctly.
    """
    if df.empty:
        return None
    match = df[df["datetime_block"] == pd.Timestamp(target_time)]
    if not match.empty:
        return round(float(match.iloc[0]["mcp_rs_mwh"]), 4)
    return None