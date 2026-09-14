from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core import db as dbm
from app.core.auth import create_access_token, get_current_user, hash_password, verify_password
from app.core.config import settings
from app.models import User
from app.schemas import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _response(user: dict) -> AuthResponse:
    return AuthResponse(access_token=create_access_token(user["_id"], user["role"]), user_id=user["_id"], full_name=user["full_name"], email=user["email"], role=user["role"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    email = body.email.lower().strip()
    role = "admin" if email in {e.lower() for e in settings.admin_emails} else "learner"
    doc = User(full_name=body.full_name.strip(), email=email, password_hash=hash_password(body.password), role=role).to_doc()
    try:
        dbm.insert(dbm.USERS, doc)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    return _response(doc)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest):
    user = dbm.find_one(dbm.USERS, {"email": body.email.lower().strip()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    return _response(user)


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"user_id": user["_id"], "full_name": user["full_name"], "email": user["email"], "role": user["role"]}
