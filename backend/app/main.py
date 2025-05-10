from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from app.core.config import settings
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.reports import router as reports_router
from app.api.users import router as users_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(auth_router.router, prefix=f"{settings.API_V1_STR}/auth", tags=["authentication"])
app.include_router(documents_router.router, prefix=f"{settings.API_V1_STR}/documents", tags=["documents"])
app.include_router(reports_router.router, prefix=f"{settings.API_V1_STR}/reports", tags=["reports"])
app.include_router(users_router.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])

@app.get("/", tags=["health"])
def health_check():
    return {"status": "healthy", "version": "1.0.0"}
