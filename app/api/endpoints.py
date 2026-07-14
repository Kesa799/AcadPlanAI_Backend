from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from typing import List
import os
import shutil
from datetime import datetime

from app.config import settings
from app.parsers import DocumentParser
from app.models.database import SessionLocal, Syllabus, CDP, CO_PO_Mapping
from app.models.schemas import SyllabusResponse, CDPResponse, GenerateRequest, ExportRequest, CDPData
from app.services.ai_service import AIService
from app.services.export_service import ExportService

router = APIRouter()
ai_service = AIService()
export_service = ExportService()

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

def _is_legacy_mock_cdp(cdp: CDP) -> bool:
    cdp_json = cdp.cdp_json or {}
    return (
        cdp.course_code == "CS101"
        and cdp.course_name == "Introduction to Computer Science"
        and cdp_json.get("course_code") == "CS101"
        and cdp_json.get("course_name") == "Introduction to Computer Science"
    )

def _repair_legacy_mock_cdp(db, cdp: CDP) -> CDP:
    if not _is_legacy_mock_cdp(cdp):
        return cdp

    syllabus = db.query(Syllabus).filter(Syllabus.id == cdp.syllabus_id).first()
    if not syllabus or not syllabus.raw_text:
        return cdp

    cdp_data = ai_service.generate_local_cdp(syllabus.raw_text, syllabus.file_path)
    cdp_data = CDPData.model_validate(cdp_data).model_dump()
    cdp.course_name = cdp_data.get("course_name", "")
    cdp.course_code = cdp_data.get("course_code", "")
    cdp.credits = cdp_data.get("credits", "")
    cdp.cdp_json = cdp_data
    cdp.concept_map = cdp_data.get("concept_map_mermaid", "")

    db.query(CO_PO_Mapping).filter(CO_PO_Mapping.cdp_id == cdp.id).delete()
    for co_id, po_scores in cdp_data.get("co_po_affinity_map", {}).items():
        for po_id, score in po_scores.items():
            db.add(CO_PO_Mapping(
                cdp_id=cdp.id,
                co_id=co_id,
                po_id=po_id,
                affinity_score=score,
                mapping_data={}
            ))

    db.commit()
    db.refresh(cdp)
    return cdp

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

@router.post("/generate", response_model=CDPResponse)
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
        
        cdp_data = ai_service.generate_cdp(syllabus.raw_text, request.additional_prompt, syllabus.file_path)
        cdp_data = CDPData.model_validate(cdp_data).model_dump()
        concept_map = cdp_data.get("concept_map_mermaid", "")
        
        cdp = CDP(
            syllabus_id=syllabus.id,
            course_name=cdp_data.get("course_name", ""),
            course_code=cdp_data.get("course_code", ""),
            credits=cdp_data.get("credits", ""),
            cdp_json=cdp_data,
            concept_map=concept_map,
            status="draft"
        )
        db.add(cdp)
        db.commit()
        db.refresh(cdp)
        
        co_po_map = cdp_data.get("co_po_affinity_map", {})
        for co_id, po_scores in co_po_map.items():
            for po_id, score in po_scores.items():
                mapping = CO_PO_Mapping(
                    cdp_id=cdp.id,
                    co_id=co_id,
                    po_id=po_id,
                    affinity_score=score,
                    mapping_data={}
                )
                db.add(mapping)
        
        db.commit()
        syllabus.status = "completed"
        db.commit()
        
        return _build_cdp_response(cdp)
        
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
        raise HTTPException(status_code=500, detail=f"CDP generation failed: {str(e)}")
    finally:
        db.close()

@router.get("/cdp/{cdp_id}", response_model=CDPResponse)
async def get_cdp(cdp_id: int):
    db = SessionLocal()
    try:
        cdp = db.query(CDP).filter(CDP.id == cdp_id).first()
        if not cdp:
            raise HTTPException(status_code=404, detail="CDP not found")

        cdp = _repair_legacy_mock_cdp(db, cdp)
        return _build_cdp_response(cdp)
    finally:
        db.close()

@router.get("/cdps", response_model=List[CDPResponse])
async def list_cdps(skip: int = 0, limit: int = 100):
    db = SessionLocal()
    try:
        cdps = db.query(CDP).order_by(CDP.id.desc()).offset(skip).limit(limit).all()
        cdps = [_repair_legacy_mock_cdp(db, cdp) for cdp in cdps]
        return [_build_cdp_response(cdp) for cdp in cdps]
    finally:
        db.close()

@router.post("/export")
async def export_cdp(request: ExportRequest):
    db = SessionLocal()
    try:
        cdp = db.query(CDP).filter(CDP.id == request.cdp_id).first()
        if not cdp:
            raise HTTPException(status_code=404, detail="CDP not found")
        
        if request.format == "pdf":
            output_path = export_service.generate_pdf(cdp)
        elif request.format == "docx":
            output_path = export_service.generate_docx(cdp)
        elif request.format == "json":
            output_path = export_service.generate_json(cdp)
        else:
            raise HTTPException(status_code=400, detail="Invalid format. Use 'pdf', 'docx', or 'json'")
        
        cdp.status = "exported"
        db.commit()
        
        # Return file (Windows compatible)
        return FileResponse(
            output_path,
            media_type="application/octet-stream",
            filename=os.path.basename(output_path)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        db.close()

@router.delete("/syllabus/{syllabus_id}")
async def delete_syllabus(syllabus_id: int):
    db = SessionLocal()
    try:
        syllabus = db.query(Syllabus).filter(Syllabus.id == syllabus_id).first()
        if not syllabus:
            raise HTTPException(status_code=404, detail="Syllabus not found")
        
        cdps = db.query(CDP).filter(CDP.syllabus_id == syllabus_id).all()
        for cdp in cdps:
            db.query(CO_PO_Mapping).filter(CO_PO_Mapping.cdp_id == cdp.id).delete()
            db.delete(cdp)
        
        if os.path.exists(syllabus.file_path):
            os.remove(syllabus.file_path)
        
        db.delete(syllabus)
        db.commit()
        
        return {"message": "Syllabus and associated data deleted successfully"}
    finally:
        db.close()
