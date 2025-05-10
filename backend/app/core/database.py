from supabase import create_client, Client
from supabase.client import ClientOptions
from .config import settings
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional, Dict, Any

# Initialize Supabase client with modern API
supabase: Client = create_client(
    settings.SUPABASE_URL, 
    settings.SUPABASE_KEY,
    options=ClientOptions(
        auto_refresh_token=True,
        persist_session=True
    )
)

def get_db() -> Client:
    return supabase

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# Function to get current user from token
async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Verify the token
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    response = supabase.table("users").select("*").eq("id", user_id).single().execute()
    
    if not response.data:
        raise credentials_exception
    
    return response.data

# Function to get current active user
async def get_current_active_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if not current_user.get("is_active"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user