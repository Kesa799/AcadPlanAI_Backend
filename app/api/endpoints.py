from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from typing import List
import os
import re
import shutil
from datetime import datetime

from app.config import settings
from app.parsers import DocumentParser
from app.models.database import SessionLocal, Syllabus, CDP, CO_PO_Mapping
from app.models.schemas import (
    SyllabusResponse,
    CDPResponse,
    GenerateRequest,
    ExportRequest,
    CDPData,
    FrontendCdpPlan,
    CoPoMatrixResponse,
    CourseMetadata,
    FrontendCourseOutcome,
    CoPoMappingRow,
    LecturePlanRow,
    EvalComponent,
    ThresholdRow,
    EvaluationAndGrading,
)
from app.services.ai_service import AIService
from app.services.export_service import ExportService
from app.services.extraction_service import ExtractionService

router = APIRouter()
ai_service = AIService()
export_service = ExportService()
extraction_service = ExtractionService()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        status=cdp.status,
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
            db.add(
                CO_PO_Mapping(
                    cdp_id=cdp.id,
                    co_id=co_id,
                    po_id=po_id,
                    affinity_score=score,
                    mapping_data={},
                )
            )

    db.commit()
    db.refresh(cdp)
    return cdp


def _get_syllabus_by_course_id(db, course_id: str):
    """Look up the most recent syllabus whose raw_text contains the course_id code."""
    syllabus = (
        db.query(Syllabus)
        .filter(Syllabus.raw_text.isnot(None))
        .filter(Syllabus.raw_text.contains(course_id))
        .order_by(Syllabus.id.desc())
        .first()
    )
    if syllabus:
        return syllabus
    # Fallback: latest syllabus overall
    return db.query(Syllabus).order_by(Syllabus.id.desc()).first()


def _get_cdp_by_course_code(db, course_code: str):
    """Look up the most recent CDP whose course_code matches."""
    return (
        db.query(CDP)
        .filter(CDP.course_code == course_code)
        .order_by(CDP.id.desc())
        .first()
    )


def _cdp_to_frontend_plan(cdp: CDP) -> FrontendCdpPlan:
    """Convert a backend CDP row into the shape the React frontend expects."""
    cdp_json = cdp.cdp_json or {}

    # -- Course metadata --
    credits_raw = cdp_json.get("credits", cdp.credits or "3-0-0-3")
    credit_parts = re.split(r"[-–]", str(credits_raw))
    credit_dict = {}
    for i, key in enumerate(["L", "T", "P", "C"]):
        credit_dict[key] = int(credit_parts[i]) if i < len(credit_parts) and credit_parts[i].isdigit() else 0

    metadata = CourseMetadata(
        code=cdp.course_code,
        name=cdp.course_name,
        academicYear=cdp_json.get("academic_year"),
        courseMentor=cdp_json.get("course_mentor"),
        preRequisites=", ".join(cdp_json.get("prerequisites", [])) or None,
        credits=credit_dict,
    )

    # -- Course outcomes --
    course_outcomes = [
        FrontendCourseOutcome(id=co.get("id", ""), description=co.get("description", ""))
        for co in cdp_json.get("course_outcomes", [])
    ]

    # -- CO-PO mappings (from the co_po_affinity_map) --
    affinity = cdp_json.get("co_po_affinity_map", {})
    # Also load from the database table for accuracy
    db = SessionLocal()
    try:
        db_mappings = db.query(CO_PO_Mapping).filter(CO_PO_Mapping.cdp_id == cdp.id).all()
        if db_mappings:
            affinity = {}
            for m in db_mappings:
                if m.co_id not in affinity:
                    affinity[m.co_id] = {}
                affinity[m.co_id][m.po_id] = m.affinity_score
    finally:
        db.close()

    # Collect all PO keys
    all_po_keys = set()
    for po_scores in affinity.values():
        all_po_keys.update(po_scores.keys())

    # Sort PO keys
    def po_sort_key(x):
        m = re.match(r"([A-Za-z]+)(\d+)", x)
        return (m.group(1), int(m.group(2))) if m else (x, 0)

    sorted_po_keys = sorted(all_po_keys, key=po_sort_key)
    # Normalise to lowercase keys for the frontend
    po_key_map = {pk: pk.lower() for pk in sorted_po_keys}

    co_po_mappings = []
    for co_id in sorted(affinity.keys()):
        row = {"co": co_id}
        for pk in sorted_po_keys:
            row[pk.lower()] = affinity[co_id].get(pk, "-")
        co_po_mappings.append(row)

    # -- Lecture plan (from weekly_plan) --
    lecture_plan = []
    for week in cdp_json.get("weekly_plan", []):
        week_num = week.get("week", 0)
        for topic in week.get("topics", []):
            lecture_plan.append(
                LecturePlanRow(
                    unit=week_num,
                    classPeriod=topic.get("duration", "") or f"Week {week_num}",
                    topic=topic.get("title", ""),
                    modeOfTeaching=", ".join(topic.get("assessment_methods", [])) or "Presentation",
                    inClassActivity=", ".join(topic.get("learning_objectives", [])) or "",
                    outClassActivity="",
                    coMapping=topic.get("prerequisites", []),
                    reference=[],
                )
            )

    # -- Evaluation and grading --
    eval_scheme = cdp_json.get("evaluation_scheme", [])
    total_marks = sum(e.get("weightage", 0) for e in eval_scheme) or 100
    components = [
        EvalComponent(
            name=e.get("component", ""),
            marks=e.get("weightage", 0),
            type="Internal" if i < len(eval_scheme) - 1 else "External",
        )
        for i, e in enumerate(eval_scheme)
    ]
    evaluation = EvaluationAndGrading(totalMarks=total_marks, components=components)

    return FrontendCdpPlan(
        status="success",
        courseMetadata=metadata,
        courseOutcomes=course_outcomes,
        coPoMappings=co_po_mappings,
        lecturePlan=lecture_plan,
        evaluationAndGrading=evaluation,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Upload syllabus (frontend calls POST /api/upload-syllabus)
# ---------------------------------------------------------------------------

@router.post("/upload-syllabus", response_model=SyllabusResponse)
async def upload_syllabus(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    # Validate file type
    allowed_extensions = [".pdf", ".docx", ".doc"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_extensions)}",
        )

    # Validate file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.MAX_FILE_SIZE // 1024 // 1024}MB",
        )

    # Save file
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    file_path = os.path.normpath(file_path)

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

    # Extract course code from text for courseId
    raw_text = parsed_data.get("raw_text", "")
    course_code_match = re.search(
        r"^\s*([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)", raw_text, re.MULTILINE
    )
    course_id = course_code_match.group(1).strip() if course_code_match else None

    # Save to database
    db = SessionLocal()
    try:
        syllabus = Syllabus(
            filename=file.filename,
            file_path=file_path,
            raw_text=raw_text,
            status="uploaded",
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
        status="success",
        upload_date=syllabus.upload_date,
        courseId=course_id,
        nextRoute="/cdp-review",
    )


# Keep the legacy /upload endpoint as an alias
@router.post("/upload", response_model=SyllabusResponse)
async def upload_syllabus_legacy(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    return await upload_syllabus(background_tasks, file)


# ---------------------------------------------------------------------------
# Generate CDP (legacy endpoint)
# ---------------------------------------------------------------------------

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
                detail="Syllabus not found. Upload a syllabus first, or pass an existing syllabus_id.",
            )

        syllabus.status = "processing"
        db.commit()

        cdp_data = ai_service.generate_cdp(
            syllabus.raw_text, request.additional_prompt, syllabus.file_path
        )
        cdp_data = CDPData.model_validate(cdp_data).model_dump()
        concept_map = cdp_data.get("concept_map_mermaid", "")

        cdp = CDP(
            syllabus_id=syllabus.id,
            course_name=cdp_data.get("course_name", ""),
            course_code=cdp_data.get("course_code", ""),
            credits=cdp_data.get("credits", ""),
            cdp_json=cdp_data,
            concept_map=concept_map,
            status="draft",
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
                    mapping_data={},
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
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"CDP generation failed: {str(e)}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /courses/{course_id}/cdp  — fetch the CDP plan for a course
# ---------------------------------------------------------------------------

@router.get("/courses/{course_id}/cdp")
async def get_course_cdp(course_id: str):
    """Return the CDP plan in the shape the React CdpReview page expects."""
    db = SessionLocal()
    try:
        cdp = _get_cdp_by_course_code(db, course_id)
        if not cdp:
            # If no CDP exists yet, try generating one from the syllabus
            syllabus = _get_syllabus_by_course_id(db, course_id)
            if not syllabus:
                raise HTTPException(status_code=404, detail=f"No CDP or syllabus found for course {course_id}")

            # Auto-generate CDP
            try:
                cdp_data = ai_service.generate_cdp(syllabus.raw_text, None, syllabus.file_path)
                cdp_data = CDPData.model_validate(cdp_data).model_dump()

                cdp = CDP(
                    syllabus_id=syllabus.id,
                    course_name=cdp_data.get("course_name", ""),
                    course_code=course_id,
                    credits=cdp_data.get("credits", ""),
                    cdp_json=cdp_data,
                    concept_map=cdp_data.get("concept_map_mermaid", ""),
                    status="draft",
                )
                db.add(cdp)
                db.commit()
                db.refresh(cdp)

                # Save CO-PO mappings
                for co_id, po_scores in cdp_data.get("co_po_affinity_map", {}).items():
                    for po_id, score in po_scores.items():
                        db.add(
                            CO_PO_Mapping(
                                cdp_id=cdp.id,
                                co_id=co_id,
                                po_id=po_id,
                                affinity_score=score,
                                mapping_data={},
                            )
                        )
                db.commit()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Auto-generation failed: {str(e)}")

        cdp = _repair_legacy_mock_cdp(db, cdp)
        return _cdp_to_frontend_plan(cdp).model_dump()

    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /courses/{course_id}/cdp/draft  — save an edited CDP draft
# ---------------------------------------------------------------------------

@router.put("/courses/{course_id}/cdp/draft")
async def save_cdp_draft(course_id: str, plan: dict):
    """Persist the frontend CDP plan back to the database."""
    db = SessionLocal()
    try:
        cdp = _get_cdp_by_course_code(db, course_id)
        if not cdp:
            raise HTTPException(status_code=404, detail=f"CDP not found for course {course_id}")

        # Convert the frontend plan back to our internal JSON shape
        metadata = plan.get("courseMetadata", {})
        credits = metadata.get("credits", {})
        credits_str = f"{credits.get('L', 0)}-{credits.get('T', 0)}-{credits.get('P', 0)}-{credits.get('C', 0)}"

        cdp.course_name = metadata.get("name", cdp.course_name)
        cdp.course_code = metadata.get("code", cdp.course_code)
        cdp.credits = credits_str
        cdp.cdp_json = plan
        cdp.updated_at = datetime.utcnow()

        # Rebuild CO-PO mappings from coPoMappings
        db.query(CO_PO_Mapping).filter(CO_PO_Mapping.cdp_id == cdp.id).delete()
        for row in plan.get("coPoMappings", []):
            co_id = row.get("co", "")
            for key, value in row.items():
                if key == "co":
                    continue
                if value and value != "-":
                    try:
                        score = float(value)
                    except (ValueError, TypeError):
                        continue
                    db.add(
                        CO_PO_Mapping(
                            cdp_id=cdp.id,
                            co_id=co_id,
                            po_id=key.upper(),
                            affinity_score=score,
                            mapping_data={},
                        )
                    )

        db.commit()
        return {"success": True}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# POST /courses/{course_id}/cdp/generate  — trigger document generation
# ---------------------------------------------------------------------------

@router.post("/courses/{course_id}/cdp/generate")
async def generate_cdp_document(course_id: str, plan: dict):
    """Generate a CDP document (save the plan and return success)."""
    db = SessionLocal()
    try:
        cdp = _get_cdp_by_course_code(db, course_id)
        if not cdp:
            raise HTTPException(status_code=404, detail=f"CDP not found for course {course_id}")

        # Save the updated plan
        cdp.cdp_json = plan
        cdp.updated_at = datetime.utcnow()
        db.commit()

        return {"success": True}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /courses/{course_id}/copo-matrix  — fetch CO-PO matrix
# ---------------------------------------------------------------------------

@router.get("/courses/{course_id}/copo-matrix")
async def get_copo_matrix(course_id: str):
    """Return the CO-PO matrix in the shape the React dashboard expects."""
    db = SessionLocal()
    try:
        cdp = _get_cdp_by_course_code(db, course_id)

        cos = ["CO1", "CO2", "CO3", "CO4", "CO5", "CO6"]
        pos = [f"PO{i}" for i in range(1, 13)]
        matrix = [["-"] * 12 for _ in range(6)]

        if cdp:
            # Load from database mappings
            mappings = db.query(CO_PO_Mapping).filter(CO_PO_Mapping.cdp_id == cdp.id).all()
            if mappings:
                co_to_idx = {co: i for i, co in enumerate(cos)}
                po_to_idx = {po: i for i, po in enumerate(pos)}
                for m in mappings:
                    co_idx = co_to_idx.get(m.co_id)
                    po_idx = po_to_idx.get(m.po_id)
                    if co_idx is not None and po_idx is not None:
                        # Convert affinity_score to 1/2/3 scale
                        score = m.affinity_score
                        if score >= 0.8:
                            matrix[co_idx][po_idx] = "3"
                        elif score >= 0.5:
                            matrix[co_idx][po_idx] = "2"
                        elif score > 0:
                            matrix[co_idx][po_idx] = "1"

            # Use actual COs from the CDP if available
            cdp_json = cdp.cdp_json or {}
            actual_cos = [co.get("id", "") for co in cdp_json.get("course_outcomes", [])]
            if actual_cos:
                cos = actual_cos + [f"CO{i}" for i in range(len(actual_cos) + 1, 7)]
                cos = cos[:6]
                # Rebuild matrix with correct number of rows
                new_matrix = [["-"] * 12 for _ in range(len(cos))]
                co_to_idx = {co: i for i, co in enumerate(actual_cos)}
                po_to_idx = {po: i for i, po in enumerate(pos)}
                for m in mappings:
                    co_idx = co_to_idx.get(m.co_id)
                    po_idx = po_to_idx.get(m.po_id)
                    if co_idx is not None and po_idx is not None:
                        score = m.affinity_score
                        if score >= 0.8:
                            new_matrix[co_idx][po_idx] = "3"
                        elif score >= 0.5:
                            new_matrix[co_idx][po_idx] = "2"
                        elif score > 0:
                            new_matrix[co_idx][po_idx] = "1"
                matrix = new_matrix

        return CoPoMatrixResponse(
            course={
                "id": course_id,
                "title": cdp.course_name if cdp else course_id,
                "academicYear": (cdp.cdp_json or {}).get("academic_year", "2026-2027") if cdp else "2026-2027",
            },
            cos=cos,
            pos=pos,
            options=["-", "1", "2", "3"],
            matrix=matrix,
        ).model_dump()

    finally:
        db.close()


# ---------------------------------------------------------------------------
# PUT /courses/{course_id}/copo-matrix  — save CO-PO matrix
# ---------------------------------------------------------------------------

@router.put("/courses/{course_id}/copo-matrix")
async def save_copo_matrix(course_id: str, matrix_data: dict):
    """Persist the CO-PO matrix from the frontend dashboard."""
    db = SessionLocal()
    try:
        cdp = _get_cdp_by_course_code(db, course_id)
        if not cdp:
            raise HTTPException(status_code=404, detail=f"CDP not found for course {course_id}")

        cos = matrix_data.get("cos", [])
        pos = matrix_data.get("pos", [])
        matrix = matrix_data.get("matrix", [])

        # Delete existing mappings
        db.query(CO_PO_Mapping).filter(CO_PO_Mapping.cdp_id == cdp.id).delete()

        # Insert new mappings
        for co_idx, co_id in enumerate(cos):
            if co_idx >= len(matrix):
                break
            for po_idx, po_id in enumerate(pos):
                if po_idx >= len(matrix[co_idx]):
                    break
                value = matrix[co_idx][po_idx]
                if value and value != "-":
                    try:
                        score_map = {"1": 0.3, "2": 0.6, "3": 1.0}
                        score = score_map.get(str(value), float(value))
                    except (ValueError, TypeError):
                        continue
                    db.add(
                        CO_PO_Mapping(
                            cdp_id=cdp.id,
                            co_id=co_id,
                            po_id=po_id,
                            affinity_score=score,
                            mapping_data={"raw_value": value},
                        )
                    )

        # Also update the co_po_affinity_map in cdp_json
        cdp_json = cdp.cdp_json or {}
        affinity = {}
        for co_idx, co_id in enumerate(cos):
            if co_idx >= len(matrix):
                break
            affinity[co_id] = {}
            for po_idx, po_id in enumerate(pos):
                if po_idx >= len(matrix[co_idx]):
                    break
                value = matrix[co_idx][po_idx]
                if value and value != "-":
                    try:
                        score_map = {"1": 0.3, "2": 0.6, "3": 1.0}
                        affinity[co_id][po_id] = score_map.get(str(value), float(value))
                    except (ValueError, TypeError):
                        pass
        cdp_json["co_po_affinity_map"] = affinity
        cdp.cdp_json = cdp_json
        cdp.updated_at = datetime.utcnow()

        db.commit()
        return {"success": True}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Legacy CDP endpoints
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

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
            raise HTTPException(
                status_code=400, detail="Invalid format. Use 'pdf', 'docx', or 'json'"
            )

        cdp.status = "exported"
        db.commit()

        return FileResponse(
            output_path,
            media_type="application/octet-stream",
            filename=os.path.basename(output_path),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Delete syllabus
# ---------------------------------------------------------------------------

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
