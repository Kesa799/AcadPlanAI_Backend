from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Float, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.config import settings

# Windows: Use check_same_thread=False for SQLite on Windows
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False}  # Required for SQLite on Windows
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Syllabus(Base):
    __tablename__ = "syllabi"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # Windows path
    raw_text = Column(Text)
    upload_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="uploaded")

class CDP(Base):
    __tablename__ = "cdps"
    
    id = Column(Integer, primary_key=True, index=True)
    syllabus_id = Column(Integer, index=True)
    course_name = Column(String(255))
    course_code = Column(String(50))
    credits = Column(String(20))
    cdp_json = Column(JSON)
    concept_map = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String(50), default="draft")

class CO_PO_Mapping(Base):
    __tablename__ = "co_po_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    cdp_id = Column(Integer, index=True)
    co_id = Column(String(20))
    po_id = Column(String(20))
    affinity_score = Column(Float)
    mapping_data = Column(JSON)

def ensure_sqlite_schema():
    """Add columns that may be missing from an existing local SQLite database."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(cdps)")).fetchall()
        column_names = {column[1] for column in columns}
        if columns and "updated_at" not in column_names:
            connection.execute(text("ALTER TABLE cdps ADD COLUMN updated_at DATETIME"))
            connection.execute(text("UPDATE cdps SET updated_at = created_at WHERE updated_at IS NULL"))


# Create tables (Windows compatible)
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()
