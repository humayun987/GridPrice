import asyncio
import sys
sys.path.append(".")

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, Organization, UserRole, UserStatus


async def seed():
    async with AsyncSessionLocal() as db:
        # Check if admin already exists
        result = await db.execute(select(User).where(User.email == "admin@tatva.in"))
        existing = result.scalar_one_or_none()
        if existing:
            print("Admin already exists, skipping.")
            return

        # Create org
        org = Organization(name="Tatva Internal")
        db.add(org)
        await db.flush()

        # Create admin user
        admin = User(
            email="admin@tatva.in",
            password_hash=hash_password("admin123"),
            role=UserRole.admin,
            status=UserStatus.active,
            organization_id=org.id,
        )
        db.add(admin)
        await db.commit()
        print("Admin seeded: admin@tatva.in / admin123")


asyncio.run(seed())