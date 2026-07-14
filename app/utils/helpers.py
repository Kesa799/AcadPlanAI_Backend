import os
import re
from datetime import datetime
from typing import List, Dict, Any
import hashlib

def validate_file_type(filename: str) -> bool:
    """Validate if file type is allowed"""
    allowed_extensions = ['.pdf', '.docx', '.doc']
    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions

def get_file_size_mb(file_path: str) -> float:
    """Get file size in MB"""
    size_bytes = os.path.getsize(file_path)
    return size_bytes / (1024 * 1024)

def generate_unique_filename(original_filename: str) -> str:
    """Generate unique filename with timestamp"""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name, ext = os.path.splitext(original_filename)
    return f"{timestamp}_{name}{ext}"

def sanitize_text(text: str) -> str:
    """Sanitize text for JSON/HTML"""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove special characters
    text = re.sub(r'[^\w\s\-.,:;!?()]', '', text)
    return text.strip()

def extract_course_code(text: str) -> str:
    """Extract course code from text"""
    pattern = r'[A-Z]{2,4}\s*\d{3,4}'
    match = re.search(pattern, text)
    return match.group().strip() if match else "CS101"

def extract_credits(text: str) -> str:
    """Extract credits in L-T-P-C format"""
    pattern = r'(\d+-\d+-\d+-\d+)'
    match = re.search(pattern, text)
    return match.group() if match else "3-0-2-4"

def calculate_hash(text: str) -> str:
    """Calculate SHA256 hash of text"""
    return hashlib.sha256(text.encode()).hexdigest()[:16]

def format_duration_minutes(minutes: int) -> str:
    """Format duration in minutes to human readable"""
    hours = minutes // 60
    mins = minutes % 60
    if hours == 0:
        return f"{mins} minutes"
    elif mins == 0:
        return f"{hours} hours"
    else:
        return f"{hours} hours {mins} minutes"

class Timer:
    """Context manager for timing operations"""
    def __enter__(self):
        self.start = datetime.utcnow()
        return self
    
    def __exit__(self, *args):
        self.end = datetime.utcnow()
        self.duration = (self.end - self.start).total_seconds()
    
    def get_duration_ms(self) -> float:
        return self.duration * 1000