"""Authentication business logic."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.services.errors import ServiceError


async def login(username: str, password: str, db: AsyncSession) -> dict:
    """Authenticate a user and return a JWT token envelope."""
    user = await db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active or not verify_password(password, user.hashed_password):
        raise ServiceError("Invalid username or password", status_code=401)

    token = create_access_token(str(user.id), {"role": user.role, "username": user.username})
    return {
        "success": True,
        "data": {
            "access_token": token,
            "token_type": "bearer",
            "role": user.role,
            "username": user.username,
        },
        "message": "Login successful",
    }
