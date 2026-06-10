import math
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import date, timedelta

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.core.redis import cache_get, cache_set, cache_delete_pattern
from app.models.user import User
from app.models.forecast import Forecast, ForecastRun
from app.models.market import HistoricalPrice

router = APIRouter(prefix="/api", tags=["forecasts"])

# TTL constants
FORECAST_TTL = 6 * 3600    # 6 hours
HISTORICAL_TTL = 12 * 3600  # 12 hours
AVAILABILITY_TTL = 3600     # 1 hour

def safe_float(v):
    if v is None:
        return None

    try:
        v = float(v)

        if math.isnan(v) or math.isinf(v):
            return None

        return v
    except Exception:
        return None

@router.get("/forecasts")
async def get_forecasts(
    market: str = Query("GDAM"),
    region: str = Query("Telangana"),
    forecast_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if forecast_date is None:
        target_date = date.today() + timedelta(days=1)
    else:
        target_date = date.fromisoformat(forecast_date)

    # Check cache first
    cache_key = f"forecast:{market}:{region}:{target_date}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # Cache miss — query DB
    run_result = await db.execute(
        select(ForecastRun)
        .where(
            ForecastRun.market == market,
            ForecastRun.region == region,
            func.date(ForecastRun.forecast_date) == target_date,
        )
        .order_by(ForecastRun.created_at.desc())
        .limit(1)
    )
    run = run_result.scalar_one_or_none()

    if not run:
        response = {
            "available": False,
            "market": market,
            "region": region,
            "forecast_date": str(target_date),
            "blocks": [],
            "message": f"No forecast available for {market} · {region} · {target_date}",
        }
        # Cache unavailable response for 30 min only
        await cache_set(cache_key, response, ttl=1800)
        return response

    blocks_result = await db.execute(
        select(Forecast)
        .where(Forecast.forecast_run_id == run.id)
        .order_by(Forecast.datetime_block)
    )
    blocks = blocks_result.scalars().all()

    response = {
        "available": True,
        "market": market,
        "region": region,
        "forecast_date": str(target_date),
        "forecast_run_id": str(run.id),
        "blocks": [
            {
                "block": i + 1,
                "datetime_block": b.datetime_block.strftime("%H:%M"),
                "predicted_price": safe_float(b.predicted_price),
                "lower_ci": safe_float(b.lower_ci),
                "upper_ci": safe_float(b.upper_ci),
            }
            for i, b in enumerate(blocks)
        ],
    }
    await cache_set(cache_key, response, ttl=FORECAST_TTL)
    return response


@router.get("/historical")
async def get_historical(
    market: str = Query("GDAM"),
    region: str = Query("Telangana"),
    price_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if price_date is None:
        target_date = date.today()
    else:
        target_date = date.fromisoformat(price_date)

    # Check cache first
    cache_key = f"historical:{market}:{region}:{target_date}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # Cache miss — query DB
    result = await db.execute(
        select(HistoricalPrice)
        .where(
            HistoricalPrice.market == market,
            HistoricalPrice.region == region,
            func.date(HistoricalPrice.datetime_block) == target_date,
        )
        .order_by(HistoricalPrice.datetime_block)
    )
    prices = result.scalars().all()

    if not prices:
        response = {
            "available": False,
            "market": market,
            "region": region,
            "price_date": str(target_date),
            "blocks": [],
            "message": f"No historical data for {market} · {region} · {target_date}",
        }
        await cache_set(cache_key, response, ttl=1800)
        return response

    response = {
        "available": True,
        "market": market,
        "region": region,
        "price_date": str(target_date),
        "blocks": [
            {
                "block": i + 1,
                "datetime_block": p.datetime_block.strftime("%H:%M"),
                "actual_price": float(p.mcp_rs_mwh),
                "cleared_buy_mw": float(p.cleared_buy_mw) if p.cleared_buy_mw else None,
                "cleared_sell_mw": float(p.cleared_sell_mw) if p.cleared_sell_mw else None,
                "demand_ratio": round(p.cleared_buy_mw / p.cleared_sell_mw, 2) if p.cleared_buy_mw and p.cleared_sell_mw and p.cleared_sell_mw != 0 else None,
            }
            for i, p in enumerate(prices)
        ],
    }
    await cache_set(cache_key, response, ttl=HISTORICAL_TTL)
    return response


@router.get("/availability")
async def get_availability(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = "availability"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    forecast_result = await db.execute(
        select(
            ForecastRun.market,
            ForecastRun.region,
            func.date(ForecastRun.forecast_date).label("date"),
        ).distinct()
        .order_by(func.date(ForecastRun.forecast_date).desc())
    )
    forecast_dates = forecast_result.all()

    historical_result = await db.execute(
        select(
            HistoricalPrice.market,
            HistoricalPrice.region,
            func.date(HistoricalPrice.datetime_block).label("date"),
        ).distinct()
        .order_by(func.date(HistoricalPrice.datetime_block).desc())
    )
    historical_dates = historical_result.all()

    response = {
        "forecasts": [
            {"market": r.market, "region": r.region, "date": str(r.date)}
            for r in forecast_dates
        ],
        "historical": [
            {"market": r.market, "region": r.region, "date": str(r.date)}
            for r in historical_dates
        ],
    }
    await cache_set(cache_key, response, ttl=AVAILABILITY_TTL)
    return response


@router.post("/refresh")
async def refresh_forecast(
    market: str = Query("GDAM"),
    region: str = Query("Telangana"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    try:
        # Only invalidate cache — do NOT re-run the pipeline
        # Re-running causes duplicate ForecastRun entries
        deleted_forecast = await cache_delete_pattern(f"forecast:{market}:{region}:*")
        deleted_avail = await cache_delete_pattern("availability")

        return {
            "status": "success",
            "message": f"Cache invalidated — {deleted_forecast + deleted_avail} keys cleared. Next request will fetch fresh from DB.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }
        
@router.get("/ci-levels")
async def get_ci_levels(
    market: str = Query("GDAM"),
    region: str = Query("Telangana"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = f"ci_levels:{market}:{region}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(Forecast.confidence_level)
        .where(
            Forecast.market == market,
            Forecast.region == region,
        )
        .distinct()
        .order_by(Forecast.confidence_level)
    )
    levels = [row[0] for row in result.all() if row[0] is not None]

    response = {
        "market": market,
        "region": region,
        "levels": levels,
        "count": len(levels),
    }
    await cache_set(cache_key, response, ttl=AVAILABILITY_TTL)
    return response