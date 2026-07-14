import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    APP_NAME: str = "AcadPlan AI Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # Define the project root explicitly to avoid path resolution issues
    # Using Path.resolve() ensures it works reliably on Windows
    BASE_DIR: Path = Path(r"C:\Users\Kesanadhini\AcadPlan-Backend").resolve()
    
    # Paths (using the / operator for clean, platform-independent joins)
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
# We convert the Path object to a string for os.makedirs
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
