import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market = Column(String, nullable=False)
    region = Column(String, nullable=False)
    forecast_date = Column(DateTime, nullable=False)
    model_run_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String, default="completed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Forecast(Base):
    __tablename__ = "forecasts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    forecast_run_id = Column(UUID(as_uuid=True), ForeignKey("forecast_runs.id"), nullable=False)
    market = Column(String, nullable=False)
    region = Column(String, nullable=False)
    datetime_block = Column(DateTime, nullable=False)
    predicted_price = Column(Float, nullable=False)
    lower_ci = Column(Float)
    upper_ci = Column(Float)
    confidence_level = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)