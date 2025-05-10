# File: /Users/nileshhanotia/Projects/Title_search/legal-title-search/backend/app/api/users/router.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import Any, Dict, Optional
from app.core.database import get_db
from pydantic import BaseModel, EmailStr
from app.core.security import get_password_hash

router = APIRouter()

# Create Pydantic models for user operations
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    firm_name: Optional[str] = None
    email: Optional[EmailStr] = None

@router.get("/me")
async def read_users_me(user_id: str = "current_user_id") -> Dict[str, Any]:
    # Initialize Supabase client
    supabase = get_db()
    
    # In a real implementation, you would get the user_id from the auth token
    # For now, we're using a placeholder
    
    # Fetch user from Supabase
    response = supabase.table("users").select("*").eq("id", user_id).execute()
    
    # Check if user exists
    if not response.data or len(response.data) == 0:
        # For demo purposes, return placeholder data
        return {
            "id": user_id,
            "email": "user@example.com",
            "full_name": "Test User",
            "firm_name": "Legal Eagles LLC",
            "is_active": True
        }
    
    return response.data[0]

@router.put("/me")
async def update_user_me(
    user_update: UserUpdate,
    user_id: str = "current_user_id"
) -> Dict[str, Any]:
    # Initialize Supabase client
    supabase = get_db()
    
    # In a real implementation, you would get the user_id from the auth token
    
    # Prepare update data
    update_data = user_update.dict(exclude_unset=True)
    
    # Update user in Supabase
    response = supabase.table("users").update(update_data).eq("id", user_id).execute()
    
    # Check if update was successful
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {"message": "User profile updated successfully", "user": response.data[0]}