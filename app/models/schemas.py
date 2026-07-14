from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
import re

# ============ REQUEST SCHEMAS ============

class SyllabusUploadRequest(BaseModel):
    """Request for uploading a syllabus"""
    filename: str
    file_size: int
    
class GenerateRequest(BaseModel):
    """Request for generating CDP from syllabus"""
    syllabus_id: int = Field(
        0,
        description="ID of the uploaded syllabus. Use 0 to generate from the latest uploaded syllabus."
    )
    additional_prompt: Optional[str] = Field(None, description="Additional instructions for AI")
    
    @validator('syllabus_id')
    def validate_syllabus_id(cls, v):
        if v < 0:
            raise ValueError("syllabus_id must be zero or positive")
        return v

class ExportRequest(BaseModel):
    """Request for exporting CDP"""
    cdp_id: int = Field(..., description="ID of the CDP to export")
    format: str = Field(..., description="Export format: pdf, docx, or json")
    
    @validator('format')
    def validate_format(cls, v):
        v = v.lower()
        if v not in ['pdf', 'docx', 'json']:
            raise ValueError("Format must be 'pdf', 'docx', or 'json'")
        return v

class UpdateCDPRequest(BaseModel):
    """Request for updating CDP data"""
    cdp_data: Dict[str, Any] = Field(..., description="Updated CDP JSON data")

# ============ RESPONSE SCHEMAS ============

class SyllabusResponse(BaseModel):
    """Response for syllabus upload"""
    id: int
    filename: str
    status: str  # uploaded, processing, completed, failed
    upload_date: datetime
    word_count: Optional[int] = None
    
    class Config:
        from_attributes = True

# ============ CDP DATA STRUCTURES ============

class Topic(BaseModel):
    """Topic within a week"""
    id: str = Field(..., description="Topic ID (T1, T2, etc.)")
    title: str = Field(..., description="Topic title")
    duration: str = Field(..., description="L-T-P format (e.g., 2-0-1)")
    description: Optional[str] = Field(None, description="Topic description")
    prerequisites: List[str] = Field(default_factory=list, description="Prerequisite topics")
    learning_objectives: List[str] = Field(default_factory=list, description="Learning objectives")
    assessment_methods: List[str] = Field(default_factory=list, description="Assessment methods")
    
    @validator('duration')
    def validate_duration(cls, v):
        pattern = r'^\d+-\d+-\d+$'
        if not re.match(pattern, v):
            raise ValueError("Duration must be in L-T-P format (e.g., 2-0-1)")
        return v

class WeekPlan(BaseModel):
    """Weekly plan structure"""
    week: int = Field(..., description="Week number", ge=1, le=52)
    topics: List[Topic] = Field(..., description="Topics covered this week")
    total_hours: str = Field(..., description="Total L-T-P hours for the week")
    
    @validator('total_hours')
    def validate_total_hours(cls, v):
        pattern = r'^\d+-\d+-\d+$'
        if not re.match(pattern, v):
            raise ValueError("Total hours must be in L-T-P format (e.g., 4-0-2)")
        return v

class CourseOutcome(BaseModel):
    """Course Outcome (CO)"""
    id: str = Field(..., description="CO ID (CO1, CO2, etc.)")
    description: str = Field(..., description="CO description")
    mapped_pos: List[str] = Field(default_factory=list, description="Mapped POs")
    
    @validator('id')
    def validate_co_id(cls, v):
        if not v.startswith('CO'):
            raise ValueError("CO ID must start with 'CO'")
        return v

class ProgramOutcome(BaseModel):
    """Program Outcome (PO)"""
    id: str = Field(..., description="PO ID (PO1, PO2, etc.)")
    description: str = Field(..., description="PO description")
    
    @validator('id')
    def validate_po_id(cls, v):
        if not v.startswith('PO'):
            raise ValueError("PO ID must start with 'PO'")
        return v

class EvaluationScheme(BaseModel):
    """Evaluation scheme component"""
    component: str = Field(..., description="Component name (Mid-sem, End-sem, etc.)")
    weightage: int = Field(..., description="Weightage percentage", ge=0, le=100)
    duration: Optional[str] = Field(None, description="Duration (e.g., 2 hours)")
    description: Optional[str] = Field(None, description="Additional description")

class Textbook(BaseModel):
    """Textbook reference"""
    title: str = Field(..., description="Book title")
    author: str = Field(..., description="Author name")
    publisher: Optional[str] = None
    year: Optional[int] = None

class CDPData(BaseModel):
    """Complete CDP data structure"""
    # Basic Info
    course_name: str = Field(..., description="Course name")
    course_code: str = Field(..., description="Course code")
    credits: str = Field(..., description="L-T-P-C format")
    department: str = Field(..., description="Department name")
    academic_year: str = Field(..., description="Academic year (e.g., 2024-25)")
    
    # Outcomes
    course_outcomes: List[CourseOutcome] = Field(..., description="Course Outcomes")
    program_outcomes: List[ProgramOutcome] = Field(..., description="Program Outcomes")
    
    # Plan
    weekly_plan: List[WeekPlan] = Field(..., description="Week-by-week plan")
    evaluation_scheme: List[EvaluationScheme] = Field(..., description="Evaluation scheme")
    
    # Maps
    co_po_affinity_map: Dict[str, Dict[str, float]] = Field(
        ..., 
        description="CO-PO affinity scores (e.g., {'CO1': {'PO1': 0.8}})"
    )
    
    # Concept Map
    concept_map_mermaid: str = Field(..., description="Mermaid.js concept map code")
    
    # Additional
    textbooks: Optional[List[Textbook]] = Field(default_factory=list, description="Textbooks")
    prerequisites: Optional[List[str]] = Field(default_factory=list, description="Course prerequisites")
    
    @validator('credits')
    def validate_credits(cls, v):
        pattern = r'^\d+-\d+-\d+-\d+$'
        if not re.match(pattern, v):
            raise ValueError("Credits must be in L-T-P-C format (e.g., 3-0-2-4)")
        return v

class CDPResponse(BaseModel):
    """Response for CDP operations"""
    id: int
    syllabus_id: int
    course_name: str
    course_code: str
    credits: str
    cdp_json: Dict[str, Any]
    concept_map: str
    created_at: datetime
    updated_at: datetime
    status: str  # draft, finalized, exported
    
    class Config:
        from_attributes = True

class CO_PO_MappingResponse(BaseModel):
    """Response for CO-PO mapping"""
    id: int
    cdp_id: int
    co_id: str
    po_id: str
    affinity_score: float
    mapping_data: Dict[str, Any]
    
    class Config:
        from_attributes = True

# ============ ERROR RESPONSES ============

class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# ============ PAGINATION ============

class PaginatedResponse(BaseModel):
    """Paginated list response"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
