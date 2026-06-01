import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class RawWeatherForecast(Base):
    __tablename__ = "raw_weather_forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region = Column(String, nullable=False)
    datetime_hour = Column(DateTime, nullable=False)
    temperature = Column(Float)
    humidity = Column(Float)
    cloud_cover = Column(Float)
    wind_speed = Column(Float)
    solar_irradiance = Column(Float)
    rain = Column(Float)                    # ← new
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class HistoricalPrice(Base):
    __tablename__ = "historical_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market = Column(String, nullable=False)
    region = Column(String, nullable=False)
    datetime_block = Column(DateTime, nullable=False)
    cleared_buy_mw = Column(Float)
    cleared_sell_mw = Column(Float)
    mcp_rs_mwh = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)