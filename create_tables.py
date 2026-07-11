import os
import sys

# Add the current directory to path
sys.path.insert(0, os.getcwd())

# Import your database models
from app.models.database import engine, Base
from app.config import settings

print("=" * 50)
print("CREATING DATABASE TABLES")
print("=" * 50)

print(f"Database URL: {settings.DATABASE_URL}")

try:
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")
    print("   - syllabi")
    print("   - cdps")
    print("   - co_po_mappings")
except Exception as e:
    print(f"Error creating tables: {str(e)}")

print("=" * 50)
