import os
from typing import Set

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


SECRET = os.getenv("JWT_SECRET", "change-me")
ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)


def get_allowed_users() -> Set[str]:
    raw = os.getenv("ALLOWED_LOGINS", "admin")
    raw = raw.strip()
    return {u.strip() for u in raw.split(",") if u.strip()}


def create_token(username: str) -> str:
    payload = {"sub": username}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        if subject not in get_allowed_users():
            raise HTTPException(status_code=403, detail="Forbidden")
        return subject
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        if subject not in get_allowed_users():
            raise HTTPException(status_code=403, detail="Forbidden")
        return subject
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
