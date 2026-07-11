import httpx
from datetime import datetime, timedelta, date
from app.core.config import get_settings

settings = get_settings()


def _get_ml_url(market: str) -> str:
    urls = {
        "GDAM": settings.ML_SERVICE_URL_GDAM,
        "DAM":  settings.ML_SERVICE_URL_DAM,
        "RTM":  settings.ML_SERVICE_URL_RTM,
    }
    url = urls.get(market)
    if not url:
        raise ValueError(f"No ML service URL configured for market: {market}")
    return url


def _is_mock(url: str) -> bool:
    return "localhost" in url or "mock" in url


async def call_ml_service(
    payload: dict,
    market: str,
    prediction_date: date,
) -> list[dict]:
    """
    Routes to correct ML service based on market.
    payload  — for GDAM/DAM: {region, prediction_date, market_data, weather_data}
               for RTM:      {prediction_date, data: [...]}  (own shape)
    prediction_date — used to convert block numbers → datetime_block values
                       (GDAM/DAM only; RTM response already includes datetime)
    """
    url = _get_ml_url(market)

    if _is_mock(url):
        return await _mock_predict(payload, market, prediction_date)
    elif market == "RTM":
        return await _real_predict_rtm(payload, url, prediction_date)
    else:
        return await _real_predict(payload, url, market, prediction_date)


# ─── Real prediction — GDAM / DAM ────────────────────────────────────────────

async def _real_predict(
    payload: dict,
    base_url: str,
    market: str,
    prediction_date: date,
) -> list[dict]:
    url = f"{base_url}/predict/{market.lower()}"
    print(f"[ML] Calling: {url}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            print(f"[ML][{market}] {response.status_code}: {response.text}")
        response.raise_for_status()
        data = response.json()

    print(f"[ML] Response received, parsing ({market})...")
    return _parse_response(data, market, prediction_date)


# ─── Real prediction — RTM ───────────────────────────────────────────────────

async def _real_predict_rtm(
    payload: dict,
    base_url: str,
    prediction_date: date,
) -> list[dict]:
    """
    RTM has a single endpoint (no /predict/{market} suffix) and a different
    payload + response shape from GDAM/DAM.
    """
    url = f"{base_url}/api/predict"
    print(f"[ML] Calling: {url}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            print(f"[ML][RTM] {response.status_code}: {response.text}")
        response.raise_for_status()
        data = response.json()

    print(f"[ML] Response received, parsing (RTM)...")
    return _parse_rtm_response(data)


# ─── Response parser — GDAM / DAM ────────────────────────────────────────────

def _parse_response(data: dict, market: str, prediction_date: date) -> list[dict]:
    """
    Parses the unified ML service response format:

    {
        "region":          "Telangana",
        "prediction_date": "2026-06-20",
        "forecast": [
            {"block": 1,  "P10": 8882.18, "P50": 10000.0, "P90": 10000.0},
            {"block": 2,  "P10": ...,      "P50": ...,      "P90": ...},
            ...
            {"block": 96, ...}
        ]
    }

    block is 1-indexed:
        block 1  → prediction_date 00:00
        block 2  → prediction_date 00:15
        block 96 → prediction_date 23:45
    """
    forecast_list = data.get("forecast", [])

    predictions = []
    for item in forecast_list:
        try:
            item = {k.upper(): v for k, v in item.items()}  # normalize keys
            block = int(item["BLOCK"])
            p10   = float(item["P10"])
            p50   = float(item["P50"])
            p90   = float(item["P90"])

            # block 1 = offset 0 min, block 96 = offset 23h 45m
            minutes  = (block - 1) * 15
            dt_block = datetime.combine(
                prediction_date, datetime.min.time()
            ) + timedelta(minutes=minutes)

            predictions.append({
                "datetime_block":   dt_block,
                "predicted_price":  round(p50, 2),
                "lower_ci":         round(p10, 2),
                "upper_ci":         round(p90, 2),
                "confidence_level": 0.80,
            })

        except Exception as e:
            print(f"[ML][{market}] Error parsing forecast block: {e}")
            continue

    print(f"[ML][{market}] Parsed {len(predictions)} predictions")
    return predictions


# ─── Response parser — RTM ───────────────────────────────────────────────────

def _parse_rtm_response(data: dict) -> list[dict]:
    """
    Parses the RTM ML service response format:

    {
        "prediction_date": "2026-06-08",
        "imputed_history_blocks": 56,
        "predictions": [
            {"datetime": "2026-06-08 00:00:00", "block": 0,
             "p10": 4627.22, "p50": 8886.68, "p90": 10000},
            ...
            {"datetime": "2026-06-08 23:45:00", "block": 95, ...}
        ]
    }

    Note the differences from GDAM/DAM:
      - key is "predictions", not "forecast"
      - block is 0-indexed (0-95), not 1-indexed
      - keys are already lowercase p10/p50/p90
      - "datetime" is given directly, so we use it as-is instead of
        recomputing from block offset (avoids any indexing mismatch)
    """
    forecast_list = data.get("predictions", [])

    imputed = data.get("imputed_history_blocks")
    if imputed:
        print(f"[ML][RTM] imputed_history_blocks: {imputed}")

    predictions = []
    for item in forecast_list:
        try:
            dt_block = datetime.strptime(item["datetime"], "%Y-%m-%d %H:%M:%S")
            p10 = float(item["p10"])
            p50 = float(item["p50"])
            p90 = float(item["p90"])

            predictions.append({
                "datetime_block":   dt_block,
                "predicted_price":  round(p50, 2),
                "lower_ci":         round(p10, 2),
                "upper_ci":         round(p90, 2),
                "confidence_level": 0.80,
            })

        except Exception as e:
            print(f"[ML][RTM] Error parsing forecast block: {e}")
            continue

    print(f"[ML][RTM] Parsed {len(predictions)} predictions")
    return predictions


# ─── Mock prediction ──────────────────────────────────────────────────────────

async def _mock_predict(
    payload: dict,
    market: str,
    prediction_date: date,
) -> list[dict]:
    """
    Active when ML service URL contains 'localhost' or 'mock'.
    Derives a base price from recent data. Handles both payload shapes:
    GDAM/DAM ("market_data" key) and RTM ("data" key).
    """
    print(f"[ML] Mock mode ({market}) — generating dummy predictions")

    if market == "RTM":
        rows = payload.get("data", [])
        recent_prices = [
            row["rtm_price"] for row in rows
            if row.get("rtm_price") is not None
        ][-96:]
    else:
        rows = payload.get("market_data", [])
        recent_prices = [
            row["mcp_rs_mwh"] for row in rows[-96:]
            if row.get("mcp_rs_mwh") is not None
        ]

    base = 4000.0
    if recent_prices:
        base = round(sum(recent_prices) / len(recent_prices), 2)

    predictions = []
    for block in range(1, 97):
        minutes  = (block - 1) * 15
        dt_block = datetime.combine(
            prediction_date, datetime.min.time()
        ) + timedelta(minutes=minutes)

        p50 = round(base * 1.02, 2)
        p10 = round(p50 * 0.92, 2)
        p90 = round(p50 * 1.08, 2)

        predictions.append({
            "datetime_block":   dt_block,
            "predicted_price":  p50,
            "lower_ci":         p10,
            "upper_ci":         p90,
            "confidence_level": 0.80,
        })

    print(f"[ML] Mock predictions generated ({market}): {len(predictions)}")
    return predictions