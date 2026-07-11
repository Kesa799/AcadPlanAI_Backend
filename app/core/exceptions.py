from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

logger = logging.getLogger(__name__)

class AppException(Exception):
    """Base application exception"""
    def __init__(self, error_code: str, message: str, status_code: int = 400, details: dict = None):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

class DocumentParseException(AppException):
    """Exception for document parsing errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            error_code="DOC_PARSE_ERROR",
            message=message,
            status_code=400,
            details=details
        )

class AIGenerationException(AppException):
    """Exception for AI generation errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            error_code="AI_GEN_ERROR",
            message=message,
            status_code=500,
            details=details
        )

class CDPNotFoundException(AppException):
    """Exception for CDP not found"""
    def __init__(self, cdp_id: int):
        super().__init__(
            error_code="CDP_NOT_FOUND",
            message=f"CDP with ID {cdp_id} not found",
            status_code=404
        )

class SyllabusNotFoundException(AppException):
    """Exception for syllabus not found"""
    def __init__(self, syllabus_id: int):
        super().__init__(
            error_code="SYLLABUS_NOT_FOUND",
            message=f"Syllabus with ID {syllabus_id} not found",
            status_code=404
        )

class ExportException(AppException):
    """Exception for export errors"""
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            error_code="EXPORT_ERROR",
            message=message,
            status_code=500,
            details=details
        )