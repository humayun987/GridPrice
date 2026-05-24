import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    export_type = Column(String, nullable=False)   # csv, xlsx, png
    status = Column(String, default="queued", nullable=False)
    file_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ScrapeRunLog(Base):
    __tablename__ = "scrape_run_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_type = Column(String, nullable=False)      # mcp_scrape, weather_fetch
    status = Column(String, nullable=False)        # success, failed, partial
    rows_written = Column(Integer, default=0)
    error_message = Column(String)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)