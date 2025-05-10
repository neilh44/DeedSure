from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# Explicitly define origins including your frontend
origins = [
   "http://localhost:5177",
   "http://127.0.0.1:5177",
   # Add any other development origins
   "http://localhost:3000",
   "http://localhost:5173",
   "http://localhost:8080",
   # Add corresponding IP addresses
   "http://127.0.0.1:3000",
   "http://127.0.0.1:5173",
   "http://127.0.0.1:8080",
   # Add Render-hosted frontend
   "https://deedsure-client.onrender.com",
]

# If settings has CORS origins, add them to our list
if settings.BACKEND_CORS_ORIGINS:
   origins.extend([str(origin) for origin in settings.BACKEND_CORS_ORIGINS])

# Set up CORS middleware with explicit configuration
app.add_middleware(
   CORSMiddleware,
   allow_origins=origins,
   allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?|https://.*\.onrender\.com",  # Allow localhost and Render domains
   allow_credentials=True,
   allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
   allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-CSRF-Token"],
   expose_headers=["Content-Disposition"],
   max_age=600,  # Cache preflight requests for 10 minutes
)

# Global OPTIONS handler to properly respond to preflight requests
@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
   origin = request.headers.get("origin", "")
   
   # Return a response with appropriate CORS headers
   return JSONResponse(
       content={},
       headers={
           "Access-Control-Allow-Origin": origin,
           "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
           "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With, X-CSRF-Token",
           "Access-Control-Allow-Credentials": "true",
           "Access-Control-Max-Age": "600",
       }
   )

# Include routers
app.include_router(auth_router.router, prefix=f"{settings.API_V1_STR}/auth", tags=["authentication"])
app.include_router(documents_router.router, prefix=f"{settings.API_V1_STR}/documents", tags=["documents"])
app.include_router(reports_router.router, prefix=f"{settings.API_V1_STR}/reports", tags=["reports"])
app.include_router(users_router.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])

@app.get("/", tags=["health"])
def health_check():
   return {"status": "healthy", "version": "1.0.0"}

# Add exception handlers for common errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
   return JSONResponse(
       status_code=exc.status_code,
       content={"detail": exc.detail},
       headers=exc.headers,
   )

# General error handler
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
   return JSONResponse(
       status_code=500,
       content={"detail": "Internal server error", "type": str(type(exc).__name__)},
   )