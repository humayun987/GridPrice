import uuid
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from zoneinfo import ZoneInfo


async def build_features_and_predict(
    db: AsyncSession,
    state: str = "Telangana",
    target_market: str = "GDAM",
) -> dict:
    """
    New pipeline — no feature engineering in backend.

    1. Compute date range: 14 days of market history + prediction day weather
    2. Fetch raw historical_prices rows (GDAM + DAM always; RTM alone for RTM)
    3. Fetch raw raw_weather_forecasts rows (history + prediction day)
    4. Build JSON payload
    5. POST to ML service /predict
    6. Parse forecast (block → datetime_block, P10/P50/P90)
    7. Save to forecast_runs + forecasts tables
    """
    print(f"[Pipeline] Starting for {state} - {target_market}")

    try:
        today        = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        tomorrow     = today + timedelta(days=1)
        market_start = tomorrow - timedelta(days=11)

        # ── Step 1: Fetch raw market data ─────────────────────
        # DAM and GDAM models both require GDAM + DAM rows in the
        # same payload (ML service does an inner join on datetime).
        # RTM uses only its own rows (mock service, stub model).
        if target_market in ("DAM", "GDAM"):
            markets_to_fetch = ["GDAM", "DAM"]
        else:
            markets_to_fetch = [target_market]

        market_data = []
        for m in markets_to_fetch:
            rows = await _fetch_market_data(db, state, m, market_start, today)
            market_data.extend(rows)

        if not market_data:
            raise ValueError(
                f"No market data for {state}/{target_market}. "
                f"Run scraper first."
            )
        print(f"[Pipeline] Market rows fetched: {len(market_data)}")

        # ── Step 2: Fetch raw weather data ────────────────────
        # Range: market_start (inclusive) → tomorrow (inclusive)
        # Tomorrow's weather = future features the ML service needs
        weather_data = await _fetch_weather_data(
            db, state, market_start, tomorrow
        )
        if not weather_data:
            raise ValueError(
                f"No weather data for {state}. Run weather fetcher first."
            )
        print(f"[Pipeline] Weather rows fetched: {len(weather_data)}")

        # ── Step 3: Build JSON payload ─────────────────────────
        payload = {
            "region":          state,
            "prediction_date": tomorrow.strftime("%Y-%m-%d"),
            "market_data":     market_data,
            "weather_data":    weather_data,
        }

        # ── Step 4: Call ML service ───────────────────────────
        from app.services.ml_service import call_ml_service
        predictions = await call_ml_service(
            payload, market=target_market, prediction_date=tomorrow
        )
        print(f"[Pipeline] Predictions received: {len(predictions)}")

        if len(predictions) != 96:
            raise ValueError(
                f"Expected 96 predictions, got {len(predictions)}"
            )

        # ── Step 5: Save predictions ──────────────────────────
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
        return {
            "status": "failed",
            "error":  str(e),
            "state":  state,
            "market": target_market,
        }


# ─── Market data fetch ────────────────────────────────────────────────────────

async def _fetch_market_data(
    db: AsyncSession,
    state: str,
    market: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetches raw historical_prices rows for a single market.
    start_date inclusive, end_date inclusive (end of that day).
    Returns list of plain dicts — directly JSON-serialisable.
    """
    result = await db.execute(
        text("""
            SELECT
                id::text,
                market,
                region,
                datetime_block,
                mcp_rs_mwh,
                cleared_buy_mw,
                cleared_sell_mw,
                created_at
            FROM historical_prices
            WHERE
                region             = :state
                AND market         = :market
                AND datetime_block >= :start
                AND datetime_block <  :end
            ORDER BY datetime_block ASC
        """),
        {
            "state":  state,
            "market": market,
            "start":  datetime.combine(start_date, datetime.min.time()),
            "end":    datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
        }
    )

    rows = result.fetchall()
    result_list = []
    for row in rows:
        result_list.append({
            "id":              str(row.id),
            "market":          row.market,
            "region":          row.region,
            "datetime_block":  str(row.datetime_block),
            "mcp_rs_mwh":      float(row.mcp_rs_mwh)      if row.mcp_rs_mwh      is not None else None,
            "cleared_buy_mw":  float(row.cleared_buy_mw)  if row.cleared_buy_mw  is not None else None,
            "cleared_sell_mw": float(row.cleared_sell_mw) if row.cleared_sell_mw is not None else None,
            "created_at":      str(row.created_at),
        })

    return result_list


# ─── Weather data fetch ───────────────────────────────────────────────────────

async def _fetch_weather_data(
    db: AsyncSession,
    state: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetches raw raw_weather_forecasts rows.
    Covers the full historical window PLUS the prediction day,
    so the ML service can build future weather features.
    end_date is inclusive.
    """
    result = await db.execute(
        text("""
            SELECT
                id::text,
                region,
                datetime_hour,
                temperature,
                humidity,
                cloud_cover,
                wind_speed,
                solar_irradiance,
                rain,
                fetched_at
            FROM raw_weather_forecasts
            WHERE
                region            = :state
                AND datetime_hour >= :start
                AND datetime_hour <  :end
            ORDER BY datetime_hour ASC
        """),
        {
            "state": state,
            "start": datetime.combine(start_date, datetime.min.time()),
            "end":   datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
        }
    )

    rows = result.fetchall()
    result_list = []
    for row in rows:
        result_list.append({
            "id":               str(row.id),
            "region":           row.region,
            "datetime_hour":    str(row.datetime_hour),
            "temperature":      float(row.temperature)      if row.temperature      is not None else None,
            "humidity":         float(row.humidity)         if row.humidity         is not None else None,
            "cloud_cover":      float(row.cloud_cover)      if row.cloud_cover      is not None else None,
            "wind_speed":       float(row.wind_speed)       if row.wind_speed       is not None else None,
            "solar_irradiance": float(row.solar_irradiance) if row.solar_irradiance is not None else None,
            "rain":             float(row.rain)             if row.rain             is not None else None,
            "fetched_at":       str(row.fetched_at),
        })

    return result_list


# ─── Save predictions ─────────────────────────────────────────────────────────

# async def _save_predictions(
#     db: AsyncSession,
#     predictions: list[dict],
#     market: str,
#     state: str,
#     forecast_date: date,
# ) -> str:
#     """
#     Inserts 1 forecast_run row + 96 forecast rows.
#     Returns forecast_run_id.
#     """
#     forecast_run_id = str(uuid.uuid4())

#     await db.execute(
#         text("""
#             INSERT INTO forecast_runs
#                 (id, market, region, forecast_date,
#                  model_run_timestamp, status, created_at)
#             VALUES
#                 (:id, :market, :region, :forecast_date,
#                  :model_run_timestamp, :status, :created_at)
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
#                     (id, forecast_run_id, market, region,
#                      datetime_block, predicted_price,
#                      lower_ci, upper_ci, confidence_level, created_at)
#                 VALUES
#                     (:id, :forecast_run_id, :market, :region,
#                      :datetime_block, :predicted_price,
#                      :lower_ci, :upper_ci, :confidence_level, :created_at)
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

async def _save_predictions(
    db: AsyncSession,
    predictions: list[dict],
    market: str,
    state: str,
    forecast_date: date,
) -> str:
    """
    Upserts forecast_run (on market+region+forecast_date conflict, keeps same id).
    Deletes and re-inserts the 96 forecast rows tied to that run.
    """
    # ── Step 1: Upsert forecast_run, get back its id (existing or new) ──
    result = await db.execute(
        text("""
            INSERT INTO forecast_runs
                (id, market, region, forecast_date,
                 model_run_timestamp, status, created_at)
            VALUES
                (:id, :market, :region, :forecast_date,
                 :model_run_timestamp, :status, :created_at)
            ON CONFLICT (market, region, forecast_date)
            DO UPDATE SET
                model_run_timestamp = EXCLUDED.model_run_timestamp,
                status = EXCLUDED.status
            RETURNING id
        """),
        {
            "id":                  str(uuid.uuid4()),
            "market":              market,
            "region":              state,
            "forecast_date":       forecast_date,
            "model_run_timestamp": datetime.utcnow(),
            "status":              "completed",
            "created_at":          datetime.utcnow(),
        }
    )
    forecast_run_id = str(result.scalar_one())

    # ── Step 2: Clear old forecast rows for this run (safe re-run) ──
    await db.execute(
        text("DELETE FROM forecasts WHERE forecast_run_id = :run_id"),
        {"run_id": forecast_run_id}
    )

    # ── Step 3: Insert fresh predictions ──
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