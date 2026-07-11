from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse, JSONResponse
from typing import List
import os
import shutil
import json
from datetime import datetime

from app.config import settings
from app.parsers import DocumentParser
from app.models.database import SessionLocal, Syllabus, CDP
from app.models.schemas import SyllabusResponse, CDPResponse, GenerateRequest
from app.services.extraction_service import ExtractionService

router = APIRouter()
extraction_service = ExtractionService()

def _build_cdp_response(cdp: CDP) -> CDPResponse:
    return CDPResponse(
        id=cdp.id,
        syllabus_id=cdp.syllabus_id,
        course_name=cdp.course_name,
        course_code=cdp.course_code,
        credits=cdp.credits,
        cdp_json=cdp.cdp_json,
        concept_map=cdp.concept_map,
        created_at=cdp.created_at,
        updated_at=cdp.updated_at,
        status=cdp.status
    )

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/upload", response_model=SyllabusResponse)
async def upload_syllabus(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    # Validate file type
    allowed_extensions = ['.pdf', '.docx', '.doc']
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Validate file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.MAX_FILE_SIZE // 1024 // 1024}MB"
        )
    
    # Save file (Windows path handling)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    file_path = os.path.normpath(file_path)  # Normalize Windows path
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save failed: {str(e)}")
    
    # Parse document
    try:
        parsed_data = DocumentParser.parse(file_path)
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Document parsing failed: {str(e)}")
    
    # Save to database
    db = SessionLocal()
    try:
        syllabus = Syllabus(
            filename=file.filename,
            file_path=file_path,
            raw_text=parsed_data["raw_text"],
            status="uploaded"
        )
        db.add(syllabus)
        db.commit()
        db.refresh(syllabus)
    except Exception as e:
        db.rollback()
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Database save failed: {str(e)}")
    finally:
        db.close()
    
    return SyllabusResponse(
        id=syllabus.id,
        filename=syllabus.filename,
        status=syllabus.status,
        upload_date=syllabus.upload_date
    )

@router.post("/generate")
async def generate_cdp(request: GenerateRequest):
    db = SessionLocal()
    try:
        if request.syllabus_id == 0:
            syllabus = (
                db.query(Syllabus)
                .filter(Syllabus.raw_text.isnot(None))
                .order_by(Syllabus.id.desc())
                .first()
            )
        else:
            syllabus = db.query(Syllabus).filter(Syllabus.id == request.syllabus_id).first()

        if not syllabus:
            raise HTTPException(
                status_code=404,
                detail="Syllabus not found. Upload a syllabus first, or pass an existing syllabus_id."
            )
        
        syllabus.status = "processing"
        db.commit()
        
        # Rule-based text extraction without adding external/AI/hallucinated info
        extracted_data = extraction_service.extract_cdp(syllabus.raw_text)
        
        cdp = CDP(
            syllabus_id=syllabus.id,
            course_name=extracted_data.get("course_name"),
            course_code=extracted_data.get("course_code"),
            credits=extracted_data.get("credits"),
            cdp_json=extracted_data,
            concept_map="",
            status="generated"
        )
        db.add(cdp)
        db.commit()
        db.refresh(cdp)
        
        syllabus.status = "completed"
        db.commit()
        
        # Write extracted data to a JSON file in the output directory
        filename = f"CDP_{cdp.course_code or 'UNKNOWN'}_{cdp.id}.json"
        output_path = os.path.join(settings.OUTPUT_DIR, filename)
        output_path = os.path.normpath(output_path)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)
            
        # Return pretty-printed JSON directly to render inline in Swagger UI
        return Response(
            content=json.dumps(extracted_data, indent=2, ensure_ascii=False),
            media_type="application/json"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        try:
            if request.syllabus_id == 0:
                syllabus = db.query(Syllabus).order_by(Syllabus.id.desc()).first()
            else:
                syllabus = db.query(Syllabus).filter(Syllabus.id == request.syllabus_id).first()
            if syllabus:
                syllabus.status = "failed"
                db.commit()
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Extraction and JSON generation failed: {str(e)}")
    finally:
        db.close()

@router.get("/cdp/{cdp_id}", response_model=CDPResponse)
async def get_cdp(cdp_id: int):
    db = SessionLocal()
    try:
        cdp = db.query(CDP).filter(CDP.id == cdp_id).first()
        if not cdp:
            raise HTTPException(status_code=404, detail="CDP not found")
        return _build_cdp_response(cdp)
    finally:
        db.close()
