from pydantic_settings import BaseSettings
from typing import Optional, Dict, Any, List


class Settings(BaseSettings):
    PROJECT_NAME: str = "Legal Title Search API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # Supabase settings
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Groq API settings
    GROQ_API_KEY: str
    LLM_MODEL: str = "llama-3.3-70b-versatile"
    
    # CORS settings
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000", 
        "https://localhost:3000",
        "http://localhost:5176",  # Add your frontend's origin
        "https://localhost:5177",
        "https://deedsure-client.onrender.com",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()