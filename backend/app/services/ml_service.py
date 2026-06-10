import httpx
import io
import pandas as pd
from datetime import datetime
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


async def call_ml_service(csv_content: str, market: str) -> list[dict]:
    """
    Routes to correct ML service and parser based on market.
    """
    url = _get_ml_url(market)

    if _is_mock(url):
        return await _mock_predict(csv_content, market)
    else:
        return await _real_predict(csv_content, url, market)


# ─── Real prediction ──────────────────────────────────────────────────────────

async def _real_predict(csv_content: str, base_url: str, market: str) -> list[dict]:
    url = f"{base_url}/api/predict/features"
    print(f"[ML] Calling: {url}")

    csv_bytes = csv_content.encode("utf-8")
    files = {
        "file": ("features.csv", io.BytesIO(csv_bytes), "text/csv")
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, files=files)
        response.raise_for_status()
        data = response.json()

    print(f"[ML] Response received, parsing ({market})...")

    if market == "DAM":
        return _parse_response_dam(data)
    else:
        return _parse_response_gdam(data)


# ─── GDAM response parser ─────────────────────────────────────────────────────

def _parse_response_gdam(data) -> list[dict]:
    """
    Expected fields: timestamp, predicted_price, p10 (optional), p90 (optional)
    Falls back to ±8% CI if p10/p90 absent.
    """
    rows = data.get("predictions", []) if isinstance(data, dict) else data

    predictions = []
    for row in rows:
        try:
            dt_raw = (
                row.get("timestamp") or
                row.get("datetime") or
                row.get("time")
            )
            if not dt_raw:
                continue

            dt  = datetime.strptime(str(dt_raw), "%Y-%m-%d %H:%M:%S")
            p50 = float(row.get("predicted_price") or 0)
            p10 = float(row.get("p10") or round(p50 * 0.92, 2))
            p90 = float(row.get("p90") or round(p50 * 1.08, 2))

            predictions.append({
                "datetime_block":   dt,
                "predicted_price":  round(p50, 2),
                "lower_ci":         round(p10, 2),
                "upper_ci":         round(p90, 2),
                "confidence_level": 0.80,
            })

        except Exception as e:
            print(f"[ML][GDAM] Error parsing row: {e}")
            continue

    print(f"[ML][GDAM] Parsed {len(predictions)} predictions")
    return predictions


# ─── DAM response parser ──────────────────────────────────────────────────────

def _parse_response_dam(data) -> list[dict]:
    """
    Expected fields: timestamp, p50, predicted_price, regime_probability, block
    Uses p50 as predicted_price.
    CI fallback ±8% — DAM response has no p10/p90.
    regime_probability ignored for now.
    """
    rows = data.get("predictions", []) if isinstance(data, dict) else data

    predictions = []
    for row in rows:
        try:
            dt_raw = (
                row.get("timestamp") or
                row.get("datetime") or
                row.get("time")
            )
            if not dt_raw:
                continue

            dt  = datetime.strptime(str(dt_raw), "%Y-%m-%d %H:%M:%S")
            p50 = float(row.get("p50") or 0)
            p10 = round(p50 * 0.92, 2)
            p90 = round(p50 * 1.08, 2)

            predictions.append({
                "datetime_block":   dt,
                "predicted_price":  round(p50, 2),
                "lower_ci":         round(p10, 2),
                "upper_ci":         round(p90, 2),
                "confidence_level": 0.80,
            })

        except Exception as e:
            print(f"[ML][DAM] Error parsing row: {e}")
            continue

    print(f"[ML][DAM] Parsed {len(predictions)} predictions")
    return predictions


# ─── Mock prediction ──────────────────────────────────────────────────────────

async def _mock_predict(csv_content: str, market: str) -> list[dict]:
    """
    Active when ML service URL contains 'localhost' or 'mock'.
    Uses price_lag_96 as base. RTM will always hit this path until
    a real service URL is configured.
    """
    print(f"[ML] Mock mode ({market}) — generating predictions from features CSV")

    df = pd.read_csv(io.StringIO(csv_content))

    predictions = []
    for _, row in df.iterrows():
        base = float(row.get("price_lag_96", 0) or 0)
        if base == 0:
            base = 4000.0

        p50 = round(base * 1.02, 2)
        p10 = round(p50 * 0.92, 2)
        p90 = round(p50 * 1.08, 2)

        try:
            dt = datetime.strptime(str(row["datetime"]), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        predictions.append({
            "datetime_block":   dt,
            "predicted_price":  p50,
            "lower_ci":         p10,
            "upper_ci":         p90,
            "confidence_level": 0.80,
        })

    print(f"[ML] Mock predictions generated ({market}): {len(predictions)}")
    return predictions