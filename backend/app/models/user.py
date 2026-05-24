import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    standard = "standard"


class UserStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    disabled = "disabled"


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.standard, nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)