from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict
import logging
from app.core.database import get_db, get_admin_db, get_current_active_user

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/me")
async def read_users_me(
    current_user: Dict[str, Any] = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """
    Get current user.
    """
    try:
        # Use the user ID from the authenticated user
        user_id = current_user["id"]
        
        # Make sure user_id is a string
        user_id = str(user_id)
        
        logger.info(f"Getting user details for ID: {user_id}")
        
        # Try to use admin client if available
        try:
            supabase = get_admin_db()
            logger.info("Using admin client for user query")
        except Exception:
            logger.warning("Admin client not available, using regular client")
            supabase = get_db()
        
        # Query the user details
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        
        if not response.data:
            logger.warning(f"User with ID {user_id} not found in database")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return response.data[0]
    except Exception as e:
        logger.error(f"Error retrieving user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user: {str(e)}"
        )