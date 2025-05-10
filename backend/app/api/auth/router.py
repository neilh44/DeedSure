from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Any, Dict

from app.core.security import create_access_token
from app.core.database import get_db

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/api/v1/auth/login")

@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Dict[str, Any]:
    # This is a placeholder - in a real app, you'd validate with Supabase
    # For now we'll simulate a successful login
    user = {
        "id": "user-123",
        "email": form_data.username,
        "is_active": True
    }
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    access_token = create_access_token(subject=user["id"])
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@router.post("/register")
async def register(
    # user_in: UserCreate 
) -> Dict[str, Any]:
    # Placeholder for user registration
    # Would interact with Supabase for user creation
    return {"message": "Registration functionality to be implemented"}
