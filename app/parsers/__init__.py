from app.parsers.pdf_parser import PDFParser
from app.parsers.word_parser import WordParser
import os

class DocumentParser:
    @staticmethod
    def parse(file_path: str) -> dict[str, any]:
        """Unified parser for both PDF and Word"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.pdf':
            return PDFParser.extract_full(file_path)
        elif ext in ['.docx', '.doc']:
            return WordParser.extract_full(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")
    
    @staticmethod
    def get_file_type(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            return 'pdf'
        elif ext in ['.docx', '.doc']:
            return 'word'
        return 'unknown'