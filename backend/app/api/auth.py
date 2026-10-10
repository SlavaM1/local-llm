import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.schemas import AuthLogin, AuthUser
from app.services.rate_limit import login_limiter
from app.services.security import create_session, current_user, revoke_session, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def client_address(request: Request) -> str:
    return request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")


@router.post("/login", response_model=AuthUser)
def login(payload: AuthLogin, request: Request, response: Response, db: Session = Depends(get_db)) -> AuthUser:
    address = client_address(request)
    retry_after = login_limiter.check(f"login:{address}", 5)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.info("Login failed from %s", address)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token, expires_at = create_session(db, user)
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_lifetime_hours * 3600,
        expires=expires_at.astimezone(timezone.utc),
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    logger.info("Login succeeded for user_id=%s", user.id)
    return AuthUser(username=user.username)


@router.get("/me", response_model=AuthUser)
def me(user: User = Depends(current_user)) -> AuthUser:
    return AuthUser(username=user.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    settings = get_settings()
    revoke_session(db, request.cookies.get(settings.session_cookie_name))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    logger.info("Logout completed")
    return response
