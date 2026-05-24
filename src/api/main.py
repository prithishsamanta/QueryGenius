# src/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from src.api.routes.analysis import router as analysis_router

# Load environment variables
load_dotenv()

app = FastAPI(
    title="QueryGenius API",
    description="AI-Powered Database Query Optimization Platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(analysis_router)

@app.get("/")
async def root():
    """
    Health check endpoint.

    Returns:
        Basic API information
    """
    return {
        "message": "QueryGenius API",
        "version": "1.0.0",
        "status": "running",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring.

    Returns:
        Health status information
    """
    return {
        "status": "healthy",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "database": "connected"  # TODO: Add actual DB health check in Phase 2
    }