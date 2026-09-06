import json
import datetime
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Body
from fastapi.responses import FileResponse
from sqlalchemy import select, func, or_, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.documents.models import DocumentFile, DocumentJob, DocumentSegment, DocumentIssue
from app.documents.storage import document_storage
from app.documents.jobs import job_manager
from app.documents.segmenter import TokenProtector
from app.engine.pipeline import detect_language, clean_json_response
from app.providers.registry import provider_registry

router = APIRouter(prefix="/api/documents", tags=["Documents"])

SUPPORTED_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".pdf"}

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Uploads a DOCX, XLSX, PPTX, or PDF document for translation."""
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Supported: DOCX, XLSX, PPTX, PDF.")

    content = await file.read()
    saved_path = document_storage.save_original(file.filename, content)

    # Initial lightweight inspection for unit count and language detection
    file_type = ext.replace(".", "")
    unit_count = 1
    unit_label = "pages"
    detected_lang = "ja"

    try:
        parser = job_manager._get_parser(file_type)
        segments, meta = parser.parse(saved_path)
        unit_count = meta.get("unit_count", 1)
        unit_label = meta.get("unit_label", "pages")
        sample_text = " ".join([s.source_text for s in segments[:30] if s.source_text])
        if sample_text.strip():
            detected_lang = detect_language(sample_text)
    except Exception as e:
        logger.warning(f"Lightweight pre-parse inspection notice: {e}")

    doc_file = DocumentFile(
        project_id=project_id,
        filename=file.filename,
        file_type=file_type,
        file_size=len(content),
        original_path=str(saved_path),
        detected_language=detected_lang,
        unit_count=unit_count,
        unit_label=unit_label
    )
    db.add(doc_file)
    await db.commit()
    await db.refresh(doc_file)

    if doc_file.project_id:
        try:
            from app.intelligence.rag.project_rag_service import ProjectRAGService
            await ProjectRAGService.index_document_file(db, doc_file)
        except Exception as rag_err:
            logger.warning(f"RAG auto-indexing notice for {doc_file.filename}: {rag_err}")

    return {
        "id": doc_file.id,
        "filename": doc_file.filename,
        "file_type": doc_file.file_type,
        "file_size": doc_file.file_size,
        "detected_language": doc_file.detected_language,
        "unit_count": doc_file.unit_count,
        "unit_label": doc_file.unit_label,
        "created_at": doc_file.created_at.isoformat()
    }

@router.get("")
async def list_documents(
    project_id: Optional[str] = None,
    include_cloud: bool = False,
    db: AsyncSession = Depends(get_db)
):
    query = select(DocumentFile)
    if not include_cloud:
        # Default Document Repository view only displays locally uploaded formats
        local_types = ["docx", "xlsx", "pptx", "pdf"]
        query = query.where(DocumentFile.file_type.in_(local_types))

    if project_id and project_id not in ("all", "default-project", ""):
        query = query.where(
            or_(
                DocumentFile.project_id == project_id,
                DocumentFile.project_id.is_(None)
            )
        )
    query = query.order_by(DocumentFile.created_at.desc())
    res = await db.execute(query)
    docs = res.scalars().all()

    items = []
    for d in docs:
        job_res = await db.execute(
            select(DocumentJob)
            .where(DocumentJob.document_id == d.id)
            .order_by(DocumentJob.created_at.desc())
            .limit(1)
        )
        latest_job = job_res.scalar_one_or_none()
        job_data = None
        if latest_job:
            job_data = {
                "id": latest_job.id,
                "document_id": latest_job.document_id,
                "project_id": latest_job.project_id,
                "status": latest_job.status,
                "source_language": latest_job.source_language,
                "target_language": latest_job.target_language,
                "provider": latest_job.provider,
                "model": latest_job.model,
                "style": latest_job.style,
                "total_segments": latest_job.total_segments,
                "completed_segments": latest_job.completed_segments,
                "failed_segments": latest_job.failed_segments,
                "progress_percent": latest_job.progress_percent,
                "current_stage": latest_job.current_stage,
                "output_filename": latest_job.output_filename,
                "output_path": latest_job.output_path,
                "error_message": latest_job.error_message,
                "created_at": latest_job.created_at.isoformat()
            }

        items.append({
            "id": d.id,
            "project_id": d.project_id,
            "filename": d.filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "detected_language": d.detected_language,
            "unit_count": d.unit_count,
            "unit_label": d.unit_label,
            "created_at": d.created_at.isoformat(),
            "active_job": job_data
        })

    return items

@router.get("/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DocumentFile).where(DocumentFile.id == document_id))
    d = res.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Document not found.")

    job_res = await db.execute(
        select(DocumentJob)
        .where(DocumentJob.document_id == d.id)
        .order_by(DocumentJob.created_at.desc())
        .limit(1)
    )
    latest_job = job_res.scalar_one_or_none()
    job_data = None
    if latest_job:
        job_data = {
            "id": latest_job.id,
            "document_id": latest_job.document_id,
            "project_id": latest_job.project_id,
            "status": latest_job.status,
            "source_language": latest_job.source_language,
            "target_language": latest_job.target_language,
            "provider": latest_job.provider,
            "model": latest_job.model,
            "style": latest_job.style,
            "total_segments": latest_job.total_segments,
            "completed_segments": latest_job.completed_segments,
            "failed_segments": latest_job.failed_segments,
            "progress_percent": latest_job.progress_percent,
            "current_stage": latest_job.current_stage,
            "output_filename": latest_job.output_filename,
            "output_path": latest_job.output_path,
            "error_message": latest_job.error_message,
            "created_at": latest_job.created_at.isoformat()
        }

    return {
        "id": d.id,
        "project_id": d.project_id,
        "filename": d.filename,
        "file_type": d.file_type,
        "file_size": d.file_size,
        "detected_language": d.detected_language,
        "unit_count": d.unit_count,
        "unit_label": d.unit_label,
        "created_at": d.created_at.isoformat(),
        "active_job": job_data
    }

class BulkDeleteRequest(BaseModel):
    project_id: Optional[str] = None
    file_type: Optional[str] = None
    doc_ids: Optional[List[str]] = None

async def _perform_bulk_delete(
    db: AsyncSession,
    project_id: Optional[str] = None,
    file_type: Optional[str] = None,
    doc_ids: Optional[List[str]] = None
) -> dict:
    stmt = select(DocumentFile)
    if doc_ids and len(doc_ids) > 0:
        valid_ids = [i.strip() for i in doc_ids if i and i.strip()]
        if valid_ids:
            stmt = stmt.where(DocumentFile.id.in_(valid_ids))
    else:
        if project_id and project_id.strip() and project_id.strip().lower() != "all":
            stmt = stmt.where(DocumentFile.project_id == project_id.strip())
        if file_type and file_type.strip() and file_type.strip().lower() != "all":
            stmt = stmt.where(DocumentFile.file_type == file_type.strip().lower())

    docs = (await db.execute(stmt)).scalars().all()
    if not docs:
        return {"message": "Không có tài liệu nào để xóa.", "deleted_count": 0}

    from app.documents.storage import WORKING_DIR
    from app.intelligence.models import ProjectDocumentChunk

    deleted_count = 0
    for d in docs:
        document_id = d.id
        # 1. Cancel running job and clean up disk files
        try:
            stmt_jobs = select(DocumentJob).where(DocumentJob.document_id == document_id)
            jobs = (await db.execute(stmt_jobs)).scalars().all()
            for j in jobs:
                job_manager.cancel_job(j.id)
                if j.output_path:
                    try:
                        op = Path(j.output_path)
                        if op.exists():
                            op.unlink()
                    except Exception as op_err:
                        logger.debug(f"Output file unlink notice: {op_err}")
                try:
                    for wp in WORKING_DIR.glob(f"job_{j.id}_working*"):
                        if wp.exists():
                            wp.unlink()
                except Exception:
                    pass
        except Exception as job_clean_err:
            logger.debug(f"Job disk files cleanup notice: {job_clean_err}")

        # 2. Remove original file on disk
        try:
            if d.original_path:
                p = Path(d.original_path)
                if p.exists():
                    p.unlink()
        except Exception as orig_err:
            logger.debug(f"Original file unlink notice: {orig_err}")

        # 3. Clean up Project Document RAG chunks and FTS5 table
        try:
            await db.execute(
                delete(ProjectDocumentChunk).where(
                    or_(
                        ProjectDocumentChunk.file_id == document_id,
                        ProjectDocumentChunk.filename == d.filename
                    )
                )
            )
            await db.execute(
                text("DELETE FROM fts_project_documents WHERE file_id = :fid OR filename = :fn"),
                {"fid": document_id, "fn": d.filename}
            )
        except Exception as rag_err:
            logger.debug(f"RAG cleanup notice for {d.filename}: {rag_err}")

        await db.delete(d)
        deleted_count += 1

    await db.commit()
    return {"message": f"Đã xóa thành công {deleted_count} tài liệu.", "deleted_count": deleted_count}

@router.post("/bulk-delete")
async def bulk_delete_documents(
    payload: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db)
):
    """Deletes multiple documents specified by doc_ids, file_type, or project_id via JSON POST body."""
    return await _perform_bulk_delete(
        db=db,
        project_id=payload.project_id,
        file_type=payload.file_type,
        doc_ids=payload.doc_ids
    )

@router.delete("/all")
async def delete_all_documents(
    project_id: Optional[str] = None,
    file_type: Optional[str] = None,
    doc_ids: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Deletes documents matching query parameters: project_id, file_type, or doc_ids (comma-separated)."""
    parsed_ids = [i.strip() for i in doc_ids.split(",") if i.strip()] if doc_ids else None
    return await _perform_bulk_delete(
        db=db,
        project_id=project_id,
        file_type=file_type,
        doc_ids=parsed_ids
    )

@router.delete("/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DocumentFile).where(DocumentFile.id == document_id))
    d = res.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="Document not found.")

    # 1. Clean up output files and working copies on disk
    try:
        from app.documents.storage import WORKING_DIR
        stmt_jobs = select(DocumentJob).where(DocumentJob.document_id == document_id)
        jobs = (await db.execute(stmt_jobs)).scalars().all()
        for j in jobs:
            if j.output_path:
                try:
                    op = Path(j.output_path)
                    if op.exists():
                        op.unlink()
                except Exception as op_err:
                    logger.debug(f"Output file unlink notice: {op_err}")
            # Working copy
            try:
                for wp in WORKING_DIR.glob(f"job_{j.id}_working*"):
                    if wp.exists():
                        wp.unlink()
            except Exception:
                pass
    except Exception as job_clean_err:
        logger.debug(f"Job disk files cleanup notice: {job_clean_err}")

    # 2. Remove original file on disk
    try:
        p = Path(d.original_path)
        if p.exists():
            p.unlink()
    except Exception as orig_err:
        logger.debug(f"Original file unlink notice: {orig_err}")

    # 3. Clean up Project Document RAG chunks and FTS5 table
    try:
        from app.intelligence.models import ProjectDocumentChunk
        await db.execute(
            delete(ProjectDocumentChunk).where(
                or_(
                    ProjectDocumentChunk.file_id == document_id,
                    ProjectDocumentChunk.filename == d.filename
                )
            )
        )
        await db.execute(
            text("DELETE FROM fts_project_documents WHERE file_id = :fid OR filename = :fn"),
            {"fid": document_id, "fn": d.filename}
        )
    except Exception as rag_err:
        logger.debug(f"RAG cleanup notice for {d.filename}: {rag_err}")

    await db.delete(d)
    await db.commit()
    return {"message": "Document and all associated outputs and RAG indexes deleted successfully."}

@router.post("/{document_id}/analyze")
async def analyze_document(document_id: str, db: AsyncSession = Depends(get_db)):
    """Extracts structure, sheet names, slide count, and segments for configuration review."""
    res = await db.execute(select(DocumentFile).where(DocumentFile.id == document_id))
    doc_file = res.scalar_one_or_none()
    if not doc_file:
        raise HTTPException(status_code=404, detail="Document not found.")

    parser = job_manager._get_parser(doc_file.file_type)
    segments, metadata = parser.parse(Path(doc_file.original_path))

    return {
        "document_id": doc_file.id,
        "filename": doc_file.filename,
        "file_type": doc_file.file_type,
        "total_segments": len(segments),
        "metadata": metadata,
        "preview_segments": [
            {
                "index": s.segment_index,
                "text": s.source_text[:100],
                "context": s.context_hint
            } for s in segments[:5]
        ]
    }

@router.post("/{document_id}/translate")
async def start_document_translation(
    document_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Initiates an asynchronous document translation job supporting both JSON and Form data."""
    res = await db.execute(select(DocumentFile).where(DocumentFile.id == document_id))
    doc_file = res.scalar_one_or_none()
    if not doc_file:
        raise HTTPException(status_code=404, detail="Document not found.")

    content_type = request.headers.get("content-type", "").lower()

    # Defaults
    target_language = "vi"
    source_language = doc_file.detected_language or "ja"
    project_id = doc_file.project_id
    style = "business"
    provider = "gemini"
    model = "gemini-3.7-flash"
    selected_sheets = None
    translate_notes = True
    translate_images = True
    translate_tab_titles = True
    translate_sheet_names = True
    custom_output_dir = None
    custom_output_filename = None

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            body = {}
        target_language = body.get("target_language", target_language)
        req_source = body.get("source_language")
        if req_source and req_source != "auto":
            source_language = req_source
        elif not req_source or req_source == "auto":
            source_language = doc_file.detected_language or "ja"

        if body.get("project_id"):
            project_id = body.get("project_id")
        style = body.get("style", style)
        provider = body.get("provider", provider)
        if body.get("model"):
            model = str(body.get("model")).strip()
        selected_sheets = body.get("selected_sheets", body.get("selected_units", None))
        translate_notes = bool(body.get("translate_notes", translate_notes))
        translate_images = bool(body.get("translate_images", False))
        translate_tab_titles = bool(body.get("translate_tab_titles", True))
        translate_sheet_names = bool(body.get("translate_sheet_names", True))
        ocr_mode = str(body.get("ocr_mode", "paddleocr")).strip().lower()
        if body.get("custom_output_dir"):
            custom_output_dir = str(body.get("custom_output_dir")).strip()
        if body.get("target_filename"):
            custom_output_filename = str(body.get("target_filename")).strip()
        elif body.get("custom_output_filename"):
            custom_output_filename = str(body.get("custom_output_filename")).strip()
    else:
        form = await request.form()
        target_language = form.get("target_language", target_language)
        req_source = form.get("source_language")
        if req_source and req_source != "auto":
            source_language = req_source
        elif not req_source or req_source == "auto":
            source_language = doc_file.detected_language or "ja"

        if form.get("project_id"):
            project_id = form.get("project_id")
        style = form.get("style", style)
        provider = form.get("provider", provider)
        if form.get("model"):
            model = str(form.get("model")).strip()
        selected_sheets = form.get("selected_sheets", None)
        if "translate_notes" in form:
            translate_notes = str(form.get("translate_notes")).lower() in ("true", "1", "yes")
        if "translate_images" in form:
            translate_images = str(form.get("translate_images")).lower() in ("true", "1", "yes")
        if "translate_tab_titles" in form:
            translate_tab_titles = str(form.get("translate_tab_titles")).lower() in ("true", "1", "yes")
        if "translate_sheet_names" in form:
            translate_sheet_names = str(form.get("translate_sheet_names")).lower() in ("true", "1", "yes")
        ocr_mode = str(form.get("ocr_mode", "paddleocr")).strip().lower()
        if form.get("custom_output_dir"):
            custom_output_dir = str(form.get("custom_output_dir")).strip()
        if form.get("target_filename"):
            custom_output_filename = str(form.get("target_filename")).strip()
        elif form.get("custom_output_filename"):
            custom_output_filename = str(form.get("custom_output_filename")).strip()

    if source_language.lower() == target_language.lower():
        raise HTTPException(
            status_code=400,
            detail=f"Ngôn ngữ nguồn ('{source_language}') và ngôn ngữ đích ('{target_language}') không được trùng nhau. Vui lòng chọn cặp ngôn ngữ hợp lệ."
        )

    options = {
        "translate_notes": translate_notes,
        "translate_images": translate_images,
        "ocr_mode": ocr_mode,
        "translate_tab_titles": translate_tab_titles,
        "translate_sheet_names": translate_sheet_names,
        "custom_output_dir": custom_output_dir if custom_output_dir else None,
        "target_filename": custom_output_filename if custom_output_filename else None
    }

    if selected_sheets:
        if isinstance(selected_sheets, list):
            options["selected_sheets"] = selected_sheets
        elif isinstance(selected_sheets, str):
            try:
                options["selected_sheets"] = json.loads(selected_sheets)
            except Exception:
                options["selected_sheets"] = [selected_sheets]

    logger.info(f"Initiating document translation job for doc={document_id} with provider='{provider}' and model='{model}'")

    job = DocumentJob(
        document_id=doc_file.id,
        project_id=project_id,
        status="queued",
        source_language=source_language,
        target_language=target_language,
        provider=provider,
        model=model,
        style=style,
        options_json=json.dumps(options, ensure_ascii=False),
        current_stage="Job queued"
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch in background worker
    job_manager.start_job(job.id)

    return {
        "id": job.id,
        "job_id": job.id,
        "model": job.model,
        "provider": job.provider,
        "status": job.status,
        "source_language": job.source_language,
        "target_language": job.target_language,
        "message": "Translation job started successfully in background."
    }

# --- Job Control & Progress ---
@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    # Issue count
    issue_cnt = (await db.execute(select(DocumentIssue).where(DocumentIssue.job_id == job_id))).scalars().all()

    total = job.total_segments or 0
    completed = job.completed_segments or 0
    failed = job.failed_segments or 0
    pending = max(0, total - completed - failed)

    elapsed = 0
    if job.created_at:
        elapsed = max(0, int((datetime.datetime.utcnow() - job.created_at).total_seconds()))

    qa_pct = 100 if job.status in ("qa", "rendering", "completed") else (round((completed / max(1, total)) * 100) if total > 0 else 0)

    return {
        "id": job.id,
        "job_id": job.id,
        "document_id": job.document_id,
        "status": job.status,
        "provider": job.provider,
        "model": job.model,
        "style": job.style,
        "total_segments": total,
        "completed_segments": completed,
        "failed_segments": failed,
        "pending_segments": pending,
        "progress_percent": job.progress_percent,
        "progress_pct": job.progress_percent,
        "qa_pct": qa_pct,
        "elapsed_seconds": elapsed,
        "current_stage": job.current_stage,
        "phase": job.current_stage,
        "output_filename": job.output_filename,
        "output_path": job.output_path,
        "has_output": bool(job.output_path and Path(job.output_path).exists()),
        "issues_count": len(issue_cnt),
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat()
    }

@router.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str, db: AsyncSession = Depends(get_db)):
    """Endpoint for frontend polling to track progress and state transitions."""
    return await get_job_status(job_id=job_id, db=db)

@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    job_manager.pause_job(job_id)
    return {"message": "Job pause requested."}

@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    job_manager.resume_job(job_id)
    return {"message": "Job resume requested."}

@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job_manager.cancel_job(job_id)
    # Ensure database record is updated to cancelled even if not in active memory
    res = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = res.scalar_one_or_none()
    if job and job.status not in ("completed", "partially_completed"):
        job.status = "cancelled"
        job.current_stage = "Đã hủy bởi người dùng"
        await db.commit()
    return {"message": "Job cancellation requested."}

@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    try:
        body = await request.json()
    except Exception:
        body = {}

    if body.get("provider"):
        job.provider = body.get("provider")
    if body.get("model"):
        job.model = str(body.get("model")).strip()

    # Reset failed segments back to pending
    seg_res = await db.execute(select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status == "failed"))
    failed_segs = seg_res.scalars().all()
    for s in failed_segs:
        s.status = "pending"
        s.error_message = None

    job.status = "queued"
    job.error_message = None
    job.current_stage = "Job retry queued"
    await db.commit()

    job_manager.start_job(job.id)
    return {"message": "Job retry scheduled.", "job_id": job.id, "status": job.status, "model": job.model}

@router.get("/jobs/{job_id}/issues")
async def get_job_issues(job_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DocumentIssue).where(DocumentIssue.job_id == job_id))
    issues = res.scalars().all()
    return [{
        "id": i.id,
        "job_id": i.job_id,
        "segment_id": i.segment_id,
        "severity": i.severity,
        "category": i.category,
        "location_text": i.location_text,
        "location": i.location_text,
        "message": i.message,
        "created_at": i.created_at.isoformat() if i.created_at else ""
    } for i in issues]

@router.get("/jobs/{job_id}/segments")
async def get_job_segments(job_id: str, limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db)):
    """Retrieves document segments for the Review screen with total count and normalized fields."""
    count_query = select(func.count(DocumentSegment.id)).where(DocumentSegment.job_id == job_id)
    total = (await db.execute(count_query)).scalar() or 0

    query = (
        select(DocumentSegment)
        .where(DocumentSegment.job_id == job_id)
        .order_by(DocumentSegment.segment_index.asc())
        .offset(offset)
        .limit(limit)
    )
    res = await db.execute(query)
    segments = res.scalars().all()

    items = []
    for s in segments:
        unit_name = s.context_hint or f"Segment #{s.segment_index + 1}"
        items.append({
            "id": s.id,
            "segment_id": s.id,
            "job_id": s.job_id,
            "segment_index": s.segment_index,
            "unit_index": s.segment_index + 1,
            "unit_name": unit_name,
            "source_text": s.source_text,
            "translated_text": s.translated_text or "",
            "target_text": s.translated_text or "",
            "status": s.status,
            "user_edited": s.status == "user_edited",
            "context_hint": s.context_hint,
            "translatable": True,
            "error_message": s.error_message,
            "qa_status": "ok"
        })

    return {
        "total": total,
        "segments": items
    }

@router.patch("/jobs/{job_id}/segments/{segment_id}")
async def update_segment_manually(job_id: str, segment_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Allows user to manually edit and correct a segment in the Review UI."""
    res = await db.execute(select(DocumentSegment).where(DocumentSegment.id == segment_id, DocumentSegment.job_id == job_id))
    seg = res.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found.")

    new_text = None
    if "target_text" in data:
        new_text = str(data["target_text"]).strip()
    elif "translated_text" in data:
        new_text = str(data["translated_text"]).strip()

    if new_text is not None:
        seg.translated_text = new_text
        seg.status = "user_edited"
        await db.commit()
        await db.refresh(seg)

    return {
        "message": "Segment updated successfully.",
        "id": seg.id,
        "segment_id": seg.id,
        "target_text": seg.translated_text,
        "translated_text": seg.translated_text,
        "user_edited": True,
        "status": seg.status
    }

@router.post("/jobs/{job_id}/segments/{segment_id}/regenerate")
async def regenerate_segment(job_id: str, segment_id: str, db: AsyncSession = Depends(get_db)):
    """Re-translates a single segment using AI without reprocessing the entire document."""
    res = await db.execute(select(DocumentSegment).where(DocumentSegment.id == segment_id, DocumentSegment.job_id == job_id))
    seg = res.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found.")

    job_res = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = job_res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    provider = provider_registry.get_provider(job.provider) or provider_registry.get_provider("gemini")
    lang_names = {"ja": "Japanese", "vi": "Vietnamese", "en": "English"}
    src_name = lang_names.get(job.source_language.lower(), job.source_language.upper())
    tgt_name = lang_names.get(job.target_language.lower(), job.target_language.upper())

    prompt = (
        f"Translate accurately from {src_name} to {tgt_name} (style: {job.style}): \"{seg.source_text}\"\n"
        f"Context: {seg.context_hint}\n"
        f"CRITICAL: Output translation MUST be strictly in {tgt_name}. Do NOT output in {src_name}.\n"
        f"Return JSON: {{\"translated\": \"...\"}}"
    )
    system_instruction = f"You are an expert translator specializing in {src_name} to {tgt_name} IT and business documents. Preserve placeholders and structure."

    resp = await provider.generate(prompt=prompt, system_instruction=system_instruction, model=job.model)
    parsed = clean_json_response(resp.text)
    new_text = parsed.get("translated", resp.text)

    token_map = json.loads(seg.protected_tokens_json or "{}")
    restored, _ = TokenProtector.restore_tokens(new_text, token_map)

    seg.translated_text = restored
    seg.status = "translated"
    await db.commit()

    return {
        "id": seg.id,
        "segment_id": seg.id,
        "source_text": seg.source_text,
        "translated_text": seg.translated_text,
        "target_text": seg.translated_text,
        "status": seg.status,
        "user_edited": False
    }

@router.get("/jobs/{job_id}/output")
async def download_output_document(job_id: str, db: AsyncSession = Depends(get_db)):
    """Downloads the completed translated document file."""
    res = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job or not job.output_path:
        raise HTTPException(status_code=404, detail="Output file not found or job not finished.")

    file_path = Path(job.output_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Output file does not exist on disk.")

    return FileResponse(
        path=str(file_path),
        filename=job.output_filename or file_path.name,
        media_type="application/octet-stream"
    )

@router.post("/jobs/{job_id}/open-folder")
async def open_job_folder(job_id: str, db: AsyncSession = Depends(get_db)):
    """Opens the containing folder of the translated document in the native file explorer."""
    res = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = res.scalar_one_or_none()
    if not job or not job.output_path:
        raise HTTPException(status_code=404, detail="Output file not found or translation not completed.")

    output_path = Path(job.output_path).resolve()
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file does not exist on disk.")

    parent_dir = output_path.parent
    try:
        import platform
        import subprocess
        if platform.system() == "Windows":
            subprocess.Popen(f'explorer /select,"{output_path}"')
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", str(output_path)])
        else:
            subprocess.Popen(["xdg-open", str(parent_dir)])
        return {"success": True, "message": f"Opened folder: {parent_dir}", "folder": str(parent_dir)}
    except Exception as e:
        logger.error(f"Failed to open folder for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not open folder: {str(e)}")


@router.get("/common-paths")
async def get_common_paths():
    """Returns dynamic standard user paths (Desktop, Downloads, Documents) on host OS."""
    home = Path.home()
    
    desktop = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"
    
    # Handle OneDrive redirected standard folders if present
    onedrive = home / "OneDrive"
    if onedrive.exists():
        if (onedrive / "Desktop").exists():
            desktop = onedrive / "Desktop"
        if (onedrive / "Documents").exists():
            documents = onedrive / "Documents"
    
    return {
        "desktop": str(desktop.resolve()) if desktop.exists() else str(home.resolve()),
        "downloads": str(downloads.resolve()) if downloads.exists() else str(home.resolve()),
        "documents": str(documents.resolve()) if documents.exists() else str(home.resolve()),
        "default_output": "data/documents/output"
    }


@router.post("/browse-directory")
async def browse_directory(body: Optional[dict] = Body(default={})):
    """Opens a native OS folder browser dialog (TopMost) and returns the selected folder path."""
    import platform
    import asyncio

    initial_dir = (body or {}).get("initial_dir", "") if isinstance(body, dict) else ""
    valid_initial = initial_dir if (initial_dir and Path(initial_dir).exists()) else None

    def _open_dialog():
        # 1. Primary: Use Python Tkinter (Fast, native Windows IFileDialog, TopMost)
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            root.focus_force()
            selected = filedialog.askdirectory(
                initialdir=valid_initial,
                title="Chọn thư mục lưu file dịch (Save Location)",
                parent=root
            )
            root.destroy()
            if selected:
                norm_path = str(Path(selected).resolve())
                return {"success": True, "path": norm_path, "canceled": False}
            return {"success": True, "path": "", "canceled": True}
        except Exception as tk_err:
            logger.warning(f"Tkinter folder dialog notice: {tk_err}, attempting PowerShell fallback...")

        # 2. Fallback: PowerShell FolderBrowserDialog
        if platform.system() == "Windows":
            try:
                import subprocess
                escaped_init = str(valid_initial).replace("'", "''") if valid_initial else ""
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
                    "$dialog.Description = 'Chọn thư mục lưu file dịch'; "
                    "$dialog.ShowNewFolderButton = $true; "
                )
                if escaped_init:
                    ps_script += f"$dialog.SelectedPath = '{escaped_init}'; "
                ps_script += (
                    "$res = $dialog.ShowDialog(); "
                    "if ($res -eq [System.Windows.Forms.DialogResult]::OK) { "
                    "    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                    "    Write-Output $dialog.SelectedPath "
                    "}"
                )
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-STA", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=120
                )
                selected = proc.stdout.strip()
                if selected:
                    return {"success": True, "path": str(Path(selected).resolve()), "canceled": False}
                return {"success": True, "path": "", "canceled": True}
            except subprocess.TimeoutExpired:
                return {"success": False, "path": "", "canceled": True, "error": "Hộp thoại chọn thư mục đã quá thời gian chờ (Timeout)."}
            except Exception as ps_err:
                logger.error(f"Error opening Windows folder dialog: {ps_err}")
                return {"success": False, "path": "", "canceled": True, "error": str(ps_err)}
        else:
            return {"success": False, "path": "", "canceled": True, "error": "Native folder dialog is only supported on Windows host."}

    return await asyncio.to_thread(_open_dialog)

