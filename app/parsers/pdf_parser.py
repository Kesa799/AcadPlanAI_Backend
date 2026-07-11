import pdfplumber
import re
import os
from typing import Optional, List, Dict, Any

class PDFParser:
    @staticmethod
    def extract_text(file_path: str) -> str:
        """Extract text using pdfplumber only"""
        text = ""
        try:
            file_path = os.path.normpath(file_path)
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
        except Exception as e:
            raise Exception(f"PDF extraction failed: {str(e)}")
        
        if not text or len(text.strip()) < 50:
            raise ValueError("Could not extract sufficient text from PDF")
        return text
    
    @staticmethod
    def extract_tables(file_path: str) -> List[List[List[str]]]:
        """Extract tables from PDF"""
        tables = []
        try:
            file_path = os.path.normpath(file_path)
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_tables = page.extract_tables()
                    if page_tables:
                        tables.extend(page_tables)
        except Exception as e:
            print(f"Table extraction warning: {str(e)}")
        return tables
    
    @staticmethod
    def parse_syllabus_structure(text: str) -> Dict[str, str]:
        """Parse common syllabus sections using regex"""
        sections = {
            "course_name": r"(?:Course\s*Name|Title)\s*[:]\s*(.+)",
            "course_code": r"(?:Course\s*Code|Code)\s*[:]\s*(.+)",
            "credits": r"(?:L-T-P-C|Credits)\s*[:]\s*(\d+-\d+-\d+-\d+)",
            "department": r"(?:Department|Dept)\s*[:]\s*(.+)",
            "course_outcomes": r"(?:Course\s*Outcomes|COs)\s*[:]\s*(.+?)(?=\n\n|\Z)",
            "syllabus": r"(?:Syllabus|Module|Unit)\s*(.+?)(?=\n\n|\Z)",
        }
        
        result = {}
        for key, pattern in sections.items():
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            result[key] = match.group(1).strip() if match else None
        
        return result
    
    @staticmethod
    def extract_full(file_path: str) -> Dict[str, any]:
        """Complete extraction pipeline using pdfplumber"""
        file_path = os.path.normpath(file_path)
        
        try:
            text = PDFParser.extract_text(file_path)
            structured = PDFParser.parse_syllabus_structure(text)
            tables = PDFParser.extract_tables(file_path)
            
            return {
                "raw_text": text,
                "structured": structured,
                "tables": tables,
                "word_count": len(text.split())
            }
        except Exception as e:
            raise Exception(f"PDF parsing failed: {str(e)}")