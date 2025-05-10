from supabase import create_client, Client
from supabase.client import ClientOptions
from .config import settings
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta

# Set up logging
logger = logging.getLogger(__name__)

# Initialize Supabase client with modern API
try:
    supabase: Client = create_client(
        settings.SUPABASE_URL, 
        settings.SUPABASE_KEY,
        options=ClientOptions(
            auto_refresh_token=True,
            persist_session=True
        )
    )
    logger.info("Supabase client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    raise

# Try to initialize admin client if service role key is available
supabase_admin = None
try:
    if hasattr(settings, 'SUPABASE_SERVICE_ROLE_KEY') and settings.SUPABASE_SERVICE_ROLE_KEY:
        supabase_admin = create_client(
            settings.SUPABASE_URL, 
            settings.SUPABASE_SERVICE_ROLE_KEY,
            options=ClientOptions(
                auto_refresh_token=False,
                persist_session=False
            )
        )
        logger.info("Supabase admin client initialized successfully")
    else:
        logger.warning("SUPABASE_SERVICE_ROLE_KEY not found in settings, admin client not initialized")
except Exception as e:
    logger.error(f"Failed to initialize Supabase admin client: {e}")
    # Don't raise, as we want to continue even without admin client

def get_db() -> Client:
    """
    Returns the regular Supabase client for auth operations
    """
    return supabase

def get_admin_db() -> Client:
    """
    Returns the admin Supabase client with service role key for bypassing RLS.
    Falls back to the regular client if admin client is not available.
    """
    if supabase_admin is None:
        logger.warning("Admin database client not available, falling back to regular client. RLS policies will still apply.")
        return supabase  # Return regular client as fallback
    return supabase_admin

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

# Function to create a new access token
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

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
        token_expiry = payload.get("exp")
        
        if user_id is None:
            logger.warning("Missing user ID in token")
            raise credentials_exception
            
        # Check if token is about to expire and needs refresh
        if token_expiry and datetime.fromtimestamp(token_expiry) < datetime.utcnow() + timedelta(minutes=5):
            logger.info(f"Token for user {user_id} is close to expiry, consider refreshing")
            
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise credentials_exception
    
    # Get user from database
    try:
        # Try to use admin client if available to bypass RLS
        client = get_admin_db() if supabase_admin else get_db()
        response = client.table("users").select("*").eq("id", user_id).single().execute()
        
        if not response.data:
            logger.warning(f"User with ID {user_id} not found in database")
            raise credentials_exception
            
        return response.data
        
    except Exception as e:
        logger.error(f"Supabase query error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred"
        )

# Function to get current active user
async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if not current_user.get("is_active"):
        logger.warning(f"Inactive user {current_user.get('id')} attempted to access protected resource")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user

# Optional: Function to check if user has required role
async def get_current_user_with_role(
    required_role: str,
    current_user: Dict[str, Any] = Depends(get_current_active_user)
) -> Dict[str, Any]:
    user_role = current_user.get("role")
    if not user_role or user_role != required_role:
        logger.warning(f"User {current_user.get('id')} with role {user_role} attempted to access resource requiring {required_role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have the required role: {required_role}"
        )
    return current_user

# Example of how to use token refresh
async def refresh_token(refresh_token: str) -> Dict[str, str]:
    try:
        response = supabase.auth.refresh_session(refresh_token)
        new_access_token = response.access_token
        new_refresh_token = response.refresh_token
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not refresh authentication"
        )