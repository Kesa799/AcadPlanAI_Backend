from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

from app.config import settings
from app.api.endpoints import router

# Print paths when server starts
print("=" * 50)
print("ACADPLAN AI PATHS:")
print(f"Upload directory: {settings.UPLOAD_DIR}")
print(f"Output directory: {settings.OUTPUT_DIR}")
print(f"Database: {settings.DATABASE_URL}")
print("=" * 50)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AcadPlan AI Backend API - Course Delivery Plan Generator"
)

# Configure CORS (for React frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers — prefix matches what the React frontend expects (/api/...)
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} v{settings.APP_VERSION}",
        "docs": "/docs",
        "health": "/api/health"
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
