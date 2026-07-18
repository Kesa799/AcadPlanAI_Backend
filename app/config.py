import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "AcadPlan AI Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Auto-detect project root from this file's location (app/config.py -> repo root)
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # Paths
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    OUTPUT_DIR: Path = BASE_DIR / "outputs"
    MAX_FILE_SIZE: int = 10485760  # 10MB

    # Database
    DATABASE_URL: str = f"sqlite:///{(BASE_DIR / 'acadplan.db')}"

    # API Keys
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Initialize settings
settings = Settings()

# Create directories if they don't exist
os.makedirs(str(settings.UPLOAD_DIR), exist_ok=True)
os.makedirs(str(settings.OUTPUT_DIR), exist_ok=True)

# Verification Output
print("=" * 60)
print("ACADPLAN AI CONFIGURATION LOADED")
print("=" * 60)
print(f"Project root:      {settings.BASE_DIR}")
print(f"Upload directory:  {settings.UPLOAD_DIR}")
print(f"Output directory:  {settings.OUTPUT_DIR}")
print(f"Database URL:      {settings.DATABASE_URL}")
print("=" * 60)
