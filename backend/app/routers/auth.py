from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.user import User, Organization, UserRole, UserStatus
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserOut
from app.core.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register-request", status_code=201)
@limiter.limit("3/hour")
async def register_request(request: Request, payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    org_result = await db.execute(
        select(Organization).where(Organization.name == payload.organization_name)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        org = Organization(name=payload.organization_name)
        db.add(org)
        await db.flush()

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=UserRole.standard,
        status=UserStatus.pending,
        organization_id=org.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"message": "Access request submitted. You'll be notified upon approval."}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.status == UserStatus.pending:
        raise HTTPException(status_code=403, detail="Account pending admin approval")

    if user.status == UserStatus.disabled:
        raise HTTPException(status_code=403, detail="Account has been deactivated")

    token = create_access_token({"sub": str(user.id), "role": user.role.value})

    return TokenResponse(
        access_token=token,
        role=user.role.value,
        email=user.email,
        status=user.status.value,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user