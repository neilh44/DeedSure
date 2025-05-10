from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from fastapi.security import OAuth2PasswordRequestForm
from typing import Any, Dict
from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime, timedelta

from app.core.security import create_access_token
from app.core.config import settings
from app.core.database import get_db

router = APIRouter()

# Models for authentication
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str = None
    firm_name: str = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]

# Handle OPTIONS requests for CORS preflight
@router.options("/{path:path}")
async def options_route(request: Request, path: str):
    return {}

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Dict[str, Any]:
    supabase = get_db()
    
    try:
        # Authenticate with Supabase
        auth_response = supabase.auth.sign_in_with_password({
            "email": form_data.username,
            "password": form_data.password
        })
        
        # If we get here, authentication was successful
        user_id = auth_response.user.id
        
        # Get user details from our users table
        user_response = supabase.table("users").select("*").eq("id", user_id).single().execute()
        
        if not user_response.data:
            # User exists in auth but not in our users table - create an entry
            user_data = {
                "id": user_id,
                "email": auth_response.user.email,
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            }
            supabase.table("users").insert(user_data).execute()
            user = user_data
        else:
            user = user_response.data
        
        # Create access token
        access_token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name"),
                "firm_name": user.get("firm_name"),
                "is_active": user.get("is_active", True)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/login-json")
async def login_json(user_data: UserLogin = Body(...)) -> Dict[str, Any]:
    """Alternative login endpoint that accepts JSON instead of form data"""
    supabase = get_db()
    
    try:
        # Authenticate with Supabase
        auth_response = supabase.auth.sign_in_with_password({
            "email": user_data.email,
            "password": user_data.password
        })
        
        # If we get here, authentication was successful
        user_id = auth_response.user.id
        
        # Get user details from our users table
        user_response = supabase.table("users").select("*").eq("id", user_id).single().execute()
        
        if not user_response.data:
            # User exists in auth but not in our users table - create an entry
            user_data = {
                "id": user_id,
                "email": auth_response.user.email,
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            }
            supabase.table("users").insert(user_data).execute()
            user = user_data
        else:
            user = user_response.data
        
        # Create access token
        access_token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name"),
                "firm_name": user.get("firm_name"),
                "is_active": user.get("is_active", True)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/register")
async def register(user_in: UserCreate = Body(...)) -> Dict[str, Any]:
    supabase = get_db()
    
    try:
        # Create user in Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": user_in.email,
            "password": user_in.password
        })
        
        # The structure is likely different - access user ID correctly
        # Log the structure to understand it better
        print(f"Auth response structure: {auth_response}")
        
        # Try different ways to get the user ID
        if hasattr(auth_response, 'user') and hasattr(auth_response.user, 'id'):
            user_id = auth_response.user.id
        elif hasattr(auth_response, 'data') and hasattr(auth_response.data, 'user') and hasattr(auth_response.data.user, 'id'):
            user_id = auth_response.data.user.id
        elif isinstance(auth_response, dict) and 'user' in auth_response and 'id' in auth_response['user']:
            user_id = auth_response['user']['id']
        else:
            # If we can't find the user ID, print the structure and raise an error
            print(f"Auth response: {auth_response}")
            raise ValueError("Could not determine user ID from auth response")
        
        # Create user profile in our users table
        user_data = {
            "id": user_id,
            "email": user_in.email,
            "full_name": user_in.full_name,
            "firm_name": user_in.firm_name,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Insert into users table
        profile_response = supabase.table("users").insert(user_data).execute()
        
        return {
            "message": "User registered successfully",
            "user_id": user_id
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        
        # Print detailed error for debugging
        print(f"Registration error: {str(e)}")
        
        # Check for common errors
        error_message = str(e).lower()
        if "already exists" in error_message or "already registered" in error_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # General error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )
    
@router.post("/logout")
async def logout(request: Request) -> Dict[str, Any]:
    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return {"message": "No token provided, logout successful"}
    
    token = auth_header.replace("Bearer ", "")
    
    try:
        # Attempt to invalidate the token with Supabase
        supabase = get_db()
        supabase.auth.sign_out()
        
        return {"message": "Logout successful"}
    except Exception as e:
        # Even if token invalidation fails, inform client of successful logout
        return {"message": "Logout successful"}

@router.post("/refresh-token")
async def refresh_token(request: Request) -> Dict[str, Any]:
    # Extract refresh token from request
    refresh_token = request.headers.get("X-Refresh-Token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token is required"
        )
    
    try:
        # Refresh session with Supabase
        supabase = get_db()
        session_response = supabase.auth.refresh_session(refresh_token)
        
        # Get user information
        user_id = session_response.user.id
        user_response = supabase.table("users").select("*").eq("id", user_id).single().execute()
        
        if not user_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user = user_response.data
        
        # Create new access token
        access_token = create_access_token(
            subject=user_id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "full_name": user.get("full_name"),
                "firm_name": user.get("firm_name"),
                "is_active": user.get("is_active", True)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to refresh token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.post("/reset-password/request")
async def request_password_reset(email: EmailStr = Body(..., embed=True)) -> Dict[str, Any]:
    supabase = get_db()
    
    try:
        # Request password reset from Supabase
        supabase.auth.reset_password_email(email)
        
        return {"message": "Password reset email sent"}
    except Exception as e:
        # Don't reveal whether the email exists in the system
        return {"message": "If the email is registered, a password reset link has been sent"}

@router.post("/reset-password/confirm")
async def confirm_password_reset(
    password: str = Body(...),
    token: str = Body(...)
) -> Dict[str, Any]:
    supabase = get_db()
    
    try:
        # Confirm password reset with Supabase
        supabase.auth.set_auth_cookie(token)
        auth_response = supabase.auth.update_user({"password": password})
        
        return {"message": "Password has been reset successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password reset failed: {str(e)}"
        )
    
