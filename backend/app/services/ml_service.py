import httpx
import io
import pandas as pd
from datetime import datetime
from app.core.config import get_settings

settings = get_settings()


async def call_ml_service(csv_content: str) -> list[dict]:
    """
    Sends 96-row pre-computed feature CSV to ML service.
    Returns P10/P50/P90 predictions for 96 blocks.

    Endpoint: POST /api/predict/features
    Input:  CSV with 96 rows × 16 feature columns + datetime
    Output: 96 predictions with p10, p50, p90
    """
    if "localhost" in settings.ML_SERVICE_URL:
        return await _mock_predict(csv_content)
    else:
        return await _real_predict(csv_content)


# ─── Real prediction ──────────────────────────────────────────────────────────

async def _real_predict(csv_content: str) -> list[dict]:
    """
    POSTs CSV to /api/predict/features.
    Parses P10/P50/P90 response.
    """
    url = f"{settings.ML_SERVICE_URL}/api/predict/features"
    print(f"[ML] Calling: {url}")

    csv_bytes = csv_content.encode("utf-8")
    files = {
        "file": ("features.csv", io.BytesIO(csv_bytes), "text/csv")
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, files=files)
        response.raise_for_status()
        data = response.json()

    print(f"[ML] Response received, parsing...")
    return _parse_response(data)

def _parse_response(data) -> list[dict]:
    rows = []
    if isinstance(data, dict):
        rows = data.get("predictions", [])
    elif isinstance(data, list):
        rows = data

    predictions = []
    for row in rows:
        try:
            # ML returns "timestamp" field
            dt_raw = (
                row.get("timestamp") or
                row.get("datetime") or
                row.get("time")
            )
            if not dt_raw:
                continue

            dt = datetime.strptime(str(dt_raw), "%Y-%m-%d %H:%M:%S")

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
            print(f"[ML] Error parsing row: {e}")
            continue

    print(f"[ML] Parsed {len(predictions)} predictions")
    return predictions

# ─── Mock prediction ──────────────────────────────────────────────────────────

async def _mock_predict(csv_content: str) -> list[dict]:
    """
    Generates realistic mock predictions from feature CSV.
    Uses price_lag_96 (yesterday same time) as base price.
    Active when ML_SERVICE_URL contains 'localhost'.
    """
    print("[ML] Mock mode — generating predictions from features CSV")

    df = pd.read_csv(io.StringIO(csv_content))

    predictions = []
    for _, row in df.iterrows():
        # Use price_lag_96 as base (yesterday same-time GDAM price)
        base = float(row.get("price_lag_96", 0) or 0)
        if base == 0:
            base = 4000.0

        p50 = round(base * 1.02, 2)
        p10 = round(p50 * 0.92, 2)
        p90 = round(p50 * 1.08, 2)

        # Parse datetime from CSV row
        try:
            dt = datetime.strptime(str(row["datetime"]), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

        predictions.append({
            "datetime_block":  dt,
            "predicted_price": p50,
            "lower_ci":        p10,
            "upper_ci":        p90,
            "confidence_level": 0.80,
        })

    print(f"[ML] Mock predictions generated: {len(predictions)}")
    return predictions