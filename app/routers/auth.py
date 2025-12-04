from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.auth import create_token, get_allowed_users


router = APIRouter()


class LoginRequest(BaseModel):
    login: str


@router.post("/api/login")
async def login(payload: LoginRequest):
    username = payload.login.strip()
    if username in get_allowed_users():
        token = create_token(username)
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Unauthorized")
