from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.auth import create_token, get_allowed_users, get_current_user


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


@router.get("/api/verify")
async def verify_token_endpoint(current_user: str = Depends(get_current_user)):
    return {"ok": True, "user": current_user}
