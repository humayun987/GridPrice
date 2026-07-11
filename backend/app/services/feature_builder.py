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

    GDAM / DAM path (unchanged):
      1. Compute date range: 14 days of market history + prediction day weather
      2. Fetch raw historical_prices rows (GDAM + DAM always)
      3. Fetch raw raw_weather_forecasts rows (history + prediction day)
      4. Build JSON payload
      5. POST to ML service /predict/{market}
      6. Parse forecast (block → datetime_block, P10/P50/P90)
      7. Save to forecast_runs + forecasts tables

    RTM path (new):
      1. Date range: D-3 to D (4 days, 96 blocks each)
      2. rtm_price: actual historical RTM prices for D-3, D-2, D-1 (D-1 may be
         partial — whatever's scraped so far); null for D
      3. dam_predicted / gdam_predicted: actual DAM/GDAM historical prices for
         D-3, D-2, D-1; DAM/GDAM *predictions* for D — fetched from the
         forecasts table (requires GDAM and DAM pipelines to have already
         completed and committed for today's run — the scheduler's
         FORECAST_MARKETS order ["GDAM", "DAM", "RTM"] guarantees this)
      4. POST to single RTM endpoint /api/predict (no market suffix)
      5. Parse response (0-indexed block, lowercase p10/p50/p90, includes datetime)
      6. Save to forecast_runs + forecasts tables (same as GDAM/DAM)
    """
    print(f"[Pipeline] Starting for {state} - {target_market}")

    if target_market == "RTM":
        return await _build_rtm_features_and_predict(db, state)

    try:
        today        = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        tomorrow     = today + timedelta(days=1)
        market_start = tomorrow - timedelta(days=11)

        # ── Step 1: Fetch raw market data ─────────────────────
        # DAM and GDAM models both require GDAM + DAM rows in the
        # same payload (ML service does an inner join on datetime).
        markets_to_fetch = ["GDAM", "DAM"]

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


# ─── RTM pipeline ──────────────────────────────────────────────────────────

def _normalize_dt_key(value) -> str:
    """
    Normalizes any datetime-like value (datetime object, or DB-stringified
    datetime with/without microseconds/timezone) into a single canonical
    "YYYY-MM-DD HH:MM:SS" string, so dict lookups always match regardless
    of where the value came from (Postgres row vs. Python-built datetime).
    Confirmed via SQL check that historical_prices.datetime_block already
    stringifies cleanly as "YYYY-MM-DD HH:MM:SS" with no microseconds —
    this is kept as a safety net, not a fix for an observed bug.
    """
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    s = str(value).strip()
    try:
        s_clean = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s_clean)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return s[:19]


async def _build_rtm_features_and_predict(
    db: AsyncSession,
    state: str = "Telangana",
) -> dict:
    """
    RTM has its own payload shape and its own endpoint (single /api/predict,
    no per-market suffix). DAM/GDAM predictions for the target day D are
    fetched from the forecasts table — this requires the GDAM and DAM
    pipelines to have already run and committed for today's scheduler pass.
    The scheduler's FORECAST_MARKETS = ["GDAM", "DAM", "RTM"] loop order
    guarantees this: each market runs to completion (success or final
    failure, all retries exhausted) before the next one starts.
    """
    try:
        today        = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        tomorrow     = today + timedelta(days=1)     # D — the day we predict
        window_start = tomorrow - timedelta(days=3)  # D-3

        # ── Step 1: DAM/GDAM predictions for D — fetch first ──
        # Fail fast here if they're missing, before doing any other work.
        dam_predictions  = await _fetch_predictions(db, state, "DAM", tomorrow)
        gdam_predictions = await _fetch_predictions(db, state, "GDAM", tomorrow)

        if not dam_predictions or not gdam_predictions:
            raise ValueError(
                f"Missing DAM/GDAM predictions for {state} on {tomorrow}. "
                f"DAM and GDAM pipelines must complete successfully before RTM runs."
            )
        if len(dam_predictions) != 96 or len(gdam_predictions) != 96:
            raise ValueError(
                f"Expected 96 DAM/GDAM predictions for {tomorrow}, "
                f"got DAM={len(dam_predictions)}, GDAM={len(gdam_predictions)}"
            )

        dam_pred_by_dt = {
            _normalize_dt_key(row["datetime_block"]): row["predicted_price"]
            for row in dam_predictions
        }
        gdam_pred_by_dt = {
            _normalize_dt_key(row["datetime_block"]): row["predicted_price"]
            for row in gdam_predictions
        }
        print(f"[Pipeline][RTM] DAM predictions: {len(dam_predictions)}, GDAM predictions: {len(gdam_predictions)}")

        # ── Step 2: Actual RTM prices for D-3, D-2, D-1 ───────
        # D-1 will typically be partial (only blocks scraped so far);
        # that's expected and handled naturally since we key by datetime.
        rtm_actuals = await _fetch_market_data(
            db, state, "RTM", window_start, today
        )
        rtm_by_dt = {
            _normalize_dt_key(row["datetime_block"]): row["mcp_rs_mwh"]
            for row in rtm_actuals
        }
        print(f"[Pipeline][RTM] Actual RTM rows fetched: {len(rtm_actuals)}")

        # ── Step 3: Actual DAM/GDAM prices for D-3, D-2, D-1 ──
        dam_actuals = await _fetch_market_data(
            db, state, "DAM", window_start, today
        )
        gdam_actuals = await _fetch_market_data(
            db, state, "GDAM", window_start, today
        )
        dam_by_dt = {
            _normalize_dt_key(row["datetime_block"]): row["mcp_rs_mwh"]
            for row in dam_actuals
        }
        gdam_by_dt = {
            _normalize_dt_key(row["datetime_block"]): row["mcp_rs_mwh"]
            for row in gdam_actuals
        }
        print(f"[Pipeline][RTM] Actual DAM rows: {len(dam_actuals)}, GDAM rows: {len(gdam_actuals)}")

        # ── Step 4: Build the 384-block payload ───────────────
        data_rows = []
        num_days = (tomorrow - window_start).days + 1  # 4: D-3, D-2, D-1, D
        for day_offset in range(num_days):
            block_date = window_start + timedelta(days=day_offset)
            is_target_day = (block_date == tomorrow)

            for block in range(96):
                dt_block = datetime.combine(
                    block_date, datetime.min.time()
                ) + timedelta(minutes=15 * block)
                dt_key = _normalize_dt_key(dt_block)

                if is_target_day:
                    rtm_price = None
                    dam_val   = dam_pred_by_dt.get(dt_key)
                    gdam_val  = gdam_pred_by_dt.get(dt_key)
                else:
                    rtm_price = rtm_by_dt.get(dt_key)  # None if not scraped yet (D-1 tail)
                    dam_val   = dam_by_dt.get(dt_key)
                    gdam_val  = gdam_by_dt.get(dt_key)

                data_rows.append({
                    "datetime":        dt_block.strftime("%Y-%m-%d %H:%M:%S"),
                    "rtm_price":       rtm_price,
                    "dam_predicted":   dam_val,
                    "gdam_predicted":  gdam_val,
                })

        payload = {
            "prediction_date": tomorrow.strftime("%Y-%m-%d"),
            "data":            data_rows,
        }
        print(f"[Pipeline][RTM] Payload built: {len(data_rows)} rows")

        # ── Step 5: Call RTM ML service ───────────────────────
        from app.services.ml_service import call_ml_service
        predictions = await call_ml_service(
            payload, market="RTM", prediction_date=tomorrow
        )
        print(f"[Pipeline][RTM] Predictions received: {len(predictions)}")

        if len(predictions) != 96:
            raise ValueError(
                f"Expected 96 RTM predictions, got {len(predictions)}"
            )

        # ── Step 6: Save predictions ──────────────────────────
        forecast_run_id = await _save_predictions(
            db, predictions, "RTM", state, tomorrow
        )
        print(f"[Pipeline][RTM] Saved run: {forecast_run_id}")

        return {
            "status":           "success",
            "forecast_run_id":  forecast_run_id,
            "blocks_predicted": len(predictions),
            "state":            state,
            "market":           "RTM",
        }

    except Exception as e:
        print(f"[Pipeline][RTM] Failed for {state}: {e}")
        return {
            "status": "failed",
            "error":  str(e),
            "state":  state,
            "market": "RTM",
        }


async def _fetch_predictions(
    db: AsyncSession,
    state: str,
    market: str,
    forecast_date: date,
) -> list[dict]:
    """
    Fetches the 96 saved prediction rows for a given market + forecast_date,
    joined through forecast_runs. Returns datetime_block + predicted_price.
    """
    result = await db.execute(
        text("""
            SELECT
                f.datetime_block,
                f.predicted_price
            FROM forecasts f
            JOIN forecast_runs fr ON fr.id = f.forecast_run_id
            WHERE
                fr.region        = :state
                AND fr.market    = :market
                AND fr.forecast_date = :forecast_date
            ORDER BY f.datetime_block ASC
        """),
        {
            "state":         state,
            "market":        market,
            "forecast_date": forecast_date,
        }
    )

    rows = result.fetchall()
    return [
        {
            "datetime_block":  row.datetime_block,
            "predicted_price": float(row.predicted_price) if row.predicted_price is not None else None,
        }
        for row in rows
    ]


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