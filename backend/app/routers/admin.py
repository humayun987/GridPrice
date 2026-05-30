from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.core.deps import require_admin
from app.models.user import User, UserStatus
from app.schemas.auth import UserOut

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=List[UserOut])
async def list_users(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User))
    return result.scalars().all()


@router.post("/approve/{user_id}")
async def approve_user(user_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status =  UserStatus.active
    await db.commit()
    return {"message": f"User {user.email} approved"}


@router.post("/reject/{user_id}")
async def reject_user(user_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status =  UserStatus.disabled
    await db.commit()
    return {"message": f"User {user.email} rejected"}


@router.post("/deactivate/{user_id}")
async def deactivate_user(user_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status =  UserStatus.disabled
    await db.commit()
    return {"message": f"User {user.email} deactivated"}