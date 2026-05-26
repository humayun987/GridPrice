import httpx
from datetime import datetime
from app.core.config import get_settings

settings = get_settings()


async def call_ml_service(payload: list[dict]) -> list[dict]:
    """
    Sends feature payload to ML service and returns predictions.

    Each item in payload has 15 features for one 15-min block.
    Returns list of predictions — one per block.

    NOW: Mock mode — returns fake predictions.
    LATER: Replace mock_predict with real_predict when ML is deployed.
    """
    if settings.ML_SERVICE_URL == "http://localhost:8001":
        # ML service not deployed yet — use mock
        return await _mock_predict(payload)
    else:
        # Real ML service is deployed
        return await _real_predict(payload)


# ─── Mock prediction (now) ────────────────────────────────────────────────────

async def _mock_predict(payload: list[dict]) -> list[dict]:
    """
    Returns fake predictions for testing.
    Simulates realistic price variation using lag_96 as base.
    Remove this when real ML service is deployed.
    """
    print(f"[ML] Mock mode — generating predictions for {len(payload)} blocks")

    predictions = []
    for block in payload:
        # Use lag_96 (yesterday same time price) as base
        # Add small variation to make it look realistic
        base_price = block.get("lag_96", 4000.0)
        if base_price == 0:
            base_price = 4000.0

        predicted = round(base_price * 1.02, 2)   # 2% above yesterday
        lower_ci  = round(predicted * 0.95, 2)     # 5% below predicted
        upper_ci  = round(predicted * 1.05, 2)     # 5% above predicted

        predictions.append({
            "datetime_block": block["datetime_block"],
            "predicted_price": predicted,
            "lower_ci": lower_ci,
            "upper_ci": upper_ci,
            "confidence_level": 0.90,
        })

    print(f"[ML] Mock predictions generated: {len(predictions)} blocks")
    return predictions


# ─── Real prediction (later) ──────────────────────────────────────────────────

async def _real_predict(payload: list[dict]) -> list[dict]:
    """
    Calls the real deployed ML service.
    Activated automatically when ML_SERVICE_URL is set in .env.
    """
    print(f"[ML] Calling real ML service at {settings.ML_SERVICE_URL}...")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.ML_SERVICE_URL}/predict",
            json={"blocks": payload}
        )
        response.raise_for_status()
        data = response.json()

    print(f"[ML] Real predictions received: {len(data['predictions'])} blocks")
    return data["predictions"]