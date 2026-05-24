import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class RawMCPSnapshot(Base):
    __tablename__ = "raw_mcp_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market = Column(String, nullable=False)        # DAM, GDAM, RTM
    region = Column(String, nullable=False)
    datetime_block = Column(DateTime, nullable=False)
    purchase_bid_mw = Column(Float)
    sell_bid_mw = Column(Float)
    mcv_mw = Column(Float)
    final_scheduled_volume_mw = Column(Float)
    mcp_rs_mwh = Column(Float, nullable=False)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class HistoricalPrice(Base):
    __tablename__ = "historical_prices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market = Column(String, nullable=False)
    region = Column(String, nullable=False)
    datetime_block = Column(DateTime, nullable=False)
    purchase_bid_mw = Column(Float)
    sell_bid_mw = Column(Float)
    mcv_mw = Column(Float)
    final_scheduled_volume_mw = Column(Float)
    mcp_rs_mwh = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)