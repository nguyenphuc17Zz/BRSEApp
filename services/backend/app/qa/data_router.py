"""QA Phase 6 REST API: sources, jobs, mappings, rules, runs, differences, reports."""
import io
import json
import re
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DATA_DIR
from app.core.database import get_db
from app.qa.data_models import (
    DataSource, DataQaJob, FieldMapping, DataQualityRule, DataSnapshot,
    DataDifference,
)
from app.qa import schemas as S
from app.qa.router import _ts
from app.qa.data_qa import readers, runner as RN
from app.qa.data_qa import rules_engine as RE

router = APIRouter(prefix="/api/qa", tags=["QA Data QA"])

UPLOAD_DIR = Path(DATA_DIR) / "data_qa" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIX = {".csv", ".xlsx", ".xls", ".json", ".txt", ".log"}


def _jl(text: str, default):
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


def ser_source(s: DataSource) -> dict:
    return {"id": s.id, "project_id": s.project_id, "name": s.name,
            "kind": s.kind, "config": _jl(s.config_json, {}),
            "schema_fields": _jl(s.schema_json, []),
            "created_by": s.created_by, "created_at": _ts(s.created_at)}


def ser_job(j: DataQaJob) -> dict:
    return {"id": j.id, "project_id": j.project_id, "job_code": j.job_code or "",
            "name": j.name, "purpose": j.purpose or "",
            "source_id": j.source_id, "dest_id": j.dest_id,
            "requirement_id": j.requirement_id, "build": j.build or "",
            "environment": j.environment or "", "owner": j.owner,
            "status": j.status, "key_fields": _jl(j.key_fields_json, []),
            "settings": _jl(j.settings_json, {}),
            "sync_tolerance_min": j.sync_tolerance_min,
            "created_by": j.created_by, "created_at": _ts(j.created_at),
            "updated_at": _ts(j.updated_at)}


def ser_mapping(m: FieldMapping) -> dict:
    return {"id": m.id, "job_id": m.job_id, "source_field": m.source_field,
            "dest_field": m.dest_field or "",
            "transform": _jl(m.transform_json, None) if m.transform_json else None,
            "ignored": m.ignored, "status": m.status,
            "ai_suggested": m.ai_suggested, "created_at": _ts(m.created_at)}


def ser_rule(r: DataQualityRule) -> dict:
    return {"id": r.id, "project_id": r.project_id, "job_id": r.job_id,
            "test_case_id": r.test_case_id, "requirement_id": r.requirement_id,
            "rule_type": r.rule_type, "definition": _jl(r.definition_json, {}),
            "status": r.status, "ai_generated": r.ai_generated,
            "created_by": r.created_by, "created_at": _ts(r.created_at)}


def ser_diff(d: DataDifference) -> dict:
    return {"id": d.id, "job_id": d.job_id, "execution_id": d.execution_id,
            "diff_type": d.diff_type, "biz_key": d.biz_key or "",
            "field": d.field, "expected": d.expected, "actual": d.actual,
            "severity": d.severity, "severity_reason": d.severity_reason,
            "rule_id": d.rule_id, "evidence": _jl(d.evidence_json, {}),
            "status": d.status, "created_at": _ts(d.created_at)}


async def _get_job(db: AsyncSession, job_id: str) -> DataQaJob:
    job = (await db.execute(select(DataQaJob).where(DataQaJob.id == job_id))).scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---------- Sources ----------
@router.post("/data-sources/upload")
async def upload_source(project_id: str, file: UploadFile = File(...),
                        name: Optional[str] = Form(None),
                        sheet: Optional[str] = Form(None),
                        kind: str = Form("file_csv"),
                        db: AsyncSession = Depends(get_db)):
    if kind not in ("file_csv", "file_excel", "file_json"):
        raise HTTPException(status_code=400, detail="Invalid kind.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {suffix or '(none)'}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 50MB limit.")
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(file.filename or "data").name)[:120]
    dest = UPLOAD_DIR / f"{project_id}_{safe}"
    dest.write_bytes(content)
    rel = dest.relative_to(Path(DATA_DIR)).as_posix()
    config: dict = {"file_path": str(Path(DATA_DIR) / rel)}
    if sheet:
        config["sheet"] = sheet
    # schema preview (first rows only)
    schema: list = []
    try:
        if kind == "file_csv":
            fields, it = readers.read_csv(config["file_path"])
            schema = fields
        elif kind == "file_excel":
            fields, warnings, it = readers.read_excel(config["file_path"], sheet or None)
            schema = fields
        else:
            fields, it = readers.read_json_records(config["file_path"])
            schema = fields
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot parse file: {e}")
    src = DataSource(project_id=project_id, name=name or file.filename or "upload",
                     kind=kind, config_json=json.dumps(config, ensure_ascii=False),
                     schema_json=json.dumps(schema, ensure_ascii=False))
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return ser_source(src)


@router.post("/data-sources", response_model=S.DataSourceResponse)
async def create_source(project_id: str, payload: S.DataSourceCreate,
                        db: AsyncSession = Depends(get_db)):
    if payload.kind not in ("file_csv", "file_excel", "file_json", "api_result",
                            "snapshot", "manual_table"):
        raise HTTPException(status_code=400, detail="Invalid kind.")
    src = DataSource(project_id=project_id, name=payload.name[:255],
                     kind=payload.kind,
                     config_json=json.dumps(payload.config or {}, ensure_ascii=False))
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return ser_source(src)


@router.get("/data-sources", response_model=List[S.DataSourceResponse])
async def list_sources(project_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(DataSource).where(
        DataSource.project_id == project_id).order_by(desc(DataSource.created_at))
    )).scalars().all()
    return [ser_source(s) for s in rows]


@router.get("/data-sources/{source_id}")
async def source_detail(source_id: str, preview: int = 20, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(DataSource).where(DataSource.id == source_id))).scalars().first()
    if not s:
        raise HTTPException(status_code=404, detail="Source not found")
    out = ser_source(s)
    try:
        fields, rows, _ = RN._source_rows(s, min(max(preview, 1), 100))
        out["preview_fields"] = fields
        out["preview_rows"] = [r for r, _ in rows]
    except Exception as e:
        out["preview_error"] = str(e)
    return out


@router.delete("/data-sources/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(DataSource).where(DataSource.id == source_id))).scalars().first()
    if not s:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(s)
    await db.commit()
    return {"status": "deleted", "id": source_id}


# ---------- Jobs ----------
@router.post("/data-jobs", response_model=S.DataJobResponse)
async def create_job(project_id: str, payload: S.DataJobCreate,
                     changed_by: str = "user", db: AsyncSession = Depends(get_db)):
    job = DataQaJob(
        project_id=project_id, job_code=await RN.next_job_code(db, project_id),
        name=payload.name[:255], purpose=payload.purpose or "",
        source_id=payload.source_id, dest_id=payload.dest_id,
        requirement_id=payload.requirement_id, build=payload.build or "",
        environment=payload.environment or "", owner=payload.owner,
        key_fields_json=json.dumps(payload.key_fields or [], ensure_ascii=False),
        settings_json=json.dumps(payload.settings or {}, ensure_ascii=False),
        sync_tolerance_min=payload.sync_tolerance_min or 0,
        created_by=changed_by)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return ser_job(job)


@router.get("/data-jobs", response_model=List[S.DataJobResponse])
async def list_jobs(project_id: str, status: Optional[str] = None,
                    search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(DataQaJob).where(
        DataQaJob.project_id == project_id).order_by(desc(DataQaJob.created_at))
    if status:
        stmt = stmt.where(DataQaJob.status == status.upper())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(DataQaJob.name.like(like), DataQaJob.job_code.like(like)))
    rows = (await db.execute(stmt.limit(200))).scalars().all()
    return [ser_job(j) for j in rows]


@router.get("/data-jobs/{job_id}")
async def job_detail(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await _get_job(db, job_id)
    out = ser_job(job)
    out["mappings"] = [ser_mapping(m) for m in (await db.execute(
        select(FieldMapping).where(FieldMapping.job_id == job_id))).scalars().all()]
    out["rules"] = [ser_rule(r) for r in (await db.execute(
        select(DataQualityRule).where(DataQualityRule.job_id == job_id))).scalars().all()]
    out["snapshots"] = [{"id": s.id, "side": s.side, "row_count": s.row_count,
                         "hash": s.content_hash[:12], "created_at": _ts(s.created_at)}
                        for s in (await db.execute(select(DataSnapshot).where(
                            DataSnapshot.job_id == job_id))).scalars().all()]
    counts = (await db.execute(select(DataDifference.diff_type, func.count(DataDifference.id)).where(
        DataDifference.job_id == job_id).group_by(DataDifference.diff_type))).all()
    out["difference_counts"] = {k: v for k, v in counts}
    return out


@router.patch("/data-jobs/{job_id}", response_model=S.DataJobResponse)
async def update_job(job_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    job = await _get_job(db, job_id)
    for k in ("name", "purpose", "source_id", "dest_id", "requirement_id",
              "build", "environment", "owner"):
        if k in payload and payload[k] is not None:
            setattr(job, k, payload[k])
    if isinstance(payload.get("key_fields"), list):
        job.key_fields_json = json.dumps(payload["key_fields"], ensure_ascii=False)
    if isinstance(payload.get("settings"), dict):
        job.settings_json = json.dumps(payload["settings"], ensure_ascii=False)
    if payload.get("sync_tolerance_min") is not None:
        job.sync_tolerance_min = int(payload["sync_tolerance_min"])
    if payload.get("status") in ("DRAFT", "READY"):
        job.status = payload["status"]
    await db.commit()
    await db.refresh(job)
    return ser_job(job)


@router.delete("/data-jobs/{job_id}")
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await _get_job(db, job_id)
    await db.delete(job)
    await db.commit()
    return {"status": "deleted", "id": job_id}


# ---------- Mappings ----------
@router.get("/data-jobs/{job_id}/mappings", response_model=List[S.FieldMappingResponse])
async def list_mappings(job_id: str, db: AsyncSession = Depends(get_db)):
    await _get_job(db, job_id)
    rows = (await db.execute(select(FieldMapping).where(
        FieldMapping.job_id == job_id).order_by(FieldMapping.source_field))).scalars().all()
    return [ser_mapping(m) for m in rows]


@router.post("/data-jobs/{job_id}/mappings")
async def create_mappings(job_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    await _get_job(db, job_id)
    items = payload.get("mappings") if isinstance(payload.get("mappings"), list) else [payload]
    out = []
    for it in items:
        if not isinstance(it, dict) or not it.get("source_field"):
            continue
        m = FieldMapping(
            job_id=job_id, source_field=str(it["source_field"])[:255],
            dest_field=str(it.get("dest_field") or it["source_field"])[:255],
            transform_json=json.dumps(it["transform"], ensure_ascii=False) if it.get("transform") else None,
            ignored=bool(it.get("ignored", False)),
            status="APPROVED" if it.get("approved") else "DRAFT",
            ai_suggested=bool(it.get("ai_suggested", False)))
        db.add(m)
        out.append(m)
    await db.commit()
    for m in out:
        await db.refresh(m)
    return [ser_mapping(m) for m in out]


@router.post("/data-jobs/{job_id}/mappings:suggest")
async def suggest_mappings(job_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """AI proposes field mappings (DRAFT). Deterministic exact-name matches included free."""
    from app.qa.llm import generate_qa_json
    from app.qa.api_testing import redact as R
    job = await _get_job(db, job_id)
    src = (await db.execute(select(DataSource).where(DataSource.id == job.source_id))).scalars().first()
    dst = (await db.execute(select(DataSource).where(DataSource.id == job.dest_id))).scalars().first()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="Job source/destination not configured.")
    try:
        src_fields, _, _ = RN._source_rows(src, 5)
        dst_fields, _, _ = RN._source_rows(dst, 5)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read sources: {e}")
    suggestions: List[dict] = []
    used_dst: set = set()
    for f in src_fields:
        if f in dst_fields:
            suggestions.append({"source_field": f, "dest_field": f,
                                "confidence": "High (exact name)", "transform": None})
            used_dst.add(f)
    remaining_src = [f for f in src_fields if f not in dst_fields]
    remaining_dst = [f for f in dst_fields if f not in used_dst]
    if remaining_src and remaining_dst:
        clean, _ = R.redact_for_ai({"src": remaining_src[:60], "dst": remaining_dst[:60]})
        parsed = await generate_qa_json(
            f"Map source fields to destination fields (Japanese/English column names). "
            f"Source: {clean['src']} Destination: {clean['dst']} "
            f"Return strict JSON: {{\"mappings\": [{{\"source_field\": \"...\", \"dest_field\": \"...\", "
            f"\"transform\": null, \"confidence\": \"...\"}}]}}",
            "You map data columns conservatively. Only map when reasonably sure.",
            (payload or {}).get("preferred_provider"), (payload or {}).get("model"),
            max_tokens=1200)
        if isinstance(parsed, dict):
            for m in (parsed.get("mappings") or [])[:60]:
                if isinstance(m, dict) and m.get("source_field") in remaining_src \
                        and m.get("dest_field") in remaining_dst:
                    suggestions.append({"source_field": m["source_field"],
                                        "dest_field": m["dest_field"],
                                        "confidence": str(m.get("confidence") or "AI Suggested")[:120],
                                        "transform": m.get("transform")})
    out = []
    for s in suggestions:
        m = FieldMapping(job_id=job_id, source_field=s["source_field"][:255],
                         dest_field=(s["dest_field"] or s["source_field"])[:255],
                         transform_json=json.dumps(s["transform"], ensure_ascii=False) if s.get("transform") else None,
                         status="DRAFT", ai_suggested=True)
        db.add(m)
        out.append(m)
    await db.commit()
    for m in out:
        await db.refresh(m)
    return [ser_mapping(m) for m in out]


@router.patch("/data-mappings/{mapping_id}", response_model=S.FieldMappingResponse)
async def update_mapping(mapping_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    m = (await db.execute(select(FieldMapping).where(FieldMapping.id == mapping_id))).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping not found")
    if payload.get("dest_field"):
        m.dest_field = str(payload["dest_field"])[:255]
    if "transform" in payload:
        m.transform_json = json.dumps(payload["transform"], ensure_ascii=False) if payload["transform"] else None
    if "ignored" in payload:
        m.ignored = bool(payload["ignored"])
    if payload.get("status") in ("DRAFT", "APPROVED"):
        m.status = payload["status"]
    await db.commit()
    await db.refresh(m)
    return ser_mapping(m)


@router.delete("/data-mappings/{mapping_id}")
async def delete_mapping(mapping_id: str, db: AsyncSession = Depends(get_db)):
    m = (await db.execute(select(FieldMapping).where(FieldMapping.id == mapping_id))).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.delete(m)
    await db.commit()
    return {"status": "deleted", "id": mapping_id}


# ---------- Rules ----------
@router.post("/data-rules", response_model=S.DataRuleResponse)
async def create_rule(project_id: str, payload: S.DataRuleCreate,
                      changed_by: str = "user", db: AsyncSession = Depends(get_db)):
    if payload.rule_type not in ("required", "unique", "range", "format", "ref_integrity",
                                 "cross_field", "calculation", "consistency", "mapping",
                                 "custom_sql"):
        raise HTTPException(status_code=400, detail="Invalid rule_type.")
    if payload.rule_type == "custom_sql":
        try:
            RE.validate_sql((payload.definition or {}).get("sql", ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    r = DataQualityRule(
        project_id=project_id, job_id=payload.job_id,
        test_case_id=payload.test_case_id, requirement_id=payload.requirement_id,
        rule_type=payload.rule_type,
        definition_json=json.dumps(payload.definition or {}, ensure_ascii=False),
        status="DRAFT", ai_generated=False, created_by=changed_by)
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return ser_rule(r)


@router.get("/data-rules", response_model=List[S.DataRuleResponse])
async def list_rules(project_id: str, job_id: Optional[str] = None,
                     status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(DataQualityRule).where(
        DataQualityRule.project_id == project_id).order_by(desc(DataQualityRule.created_at))
    if job_id:
        stmt = stmt.where(DataQualityRule.job_id == job_id)
    if status:
        stmt = stmt.where(DataQualityRule.status == status.upper())
    rows = (await db.execute(stmt.limit(300))).scalars().all()
    return [ser_rule(r) for r in rows]


@router.post("/data-rules:generate")
async def generate_rules(project_id: str, payload: dict,
                         changed_by: str = "user", db: AsyncSession = Depends(get_db)):
    """AI proposes rules from requirement + job schema. All DRAFT + AI Suggested."""
    from app.qa import engines as E1
    req_id = payload.get("requirement_id")
    if not req_id:
        raise HTTPException(status_code=400, detail="requirement_id is required.")
    req = await E1.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    fields: list = []
    if payload.get("job_id"):
        job = await _get_job(db, payload["job_id"])
        src = (await db.execute(select(DataSource).where(
            DataSource.id == job.source_id))).scalars().first()
        if src:
            try:
                fields, _, _ = RN._source_rows(src, 5)
            except Exception:
                pass
    suggestions = await RE.suggest_rules(req.title, req.description or "", fields,
                                         payload.get("preferred_provider"),
                                         payload.get("model"))
    out = []
    for s in suggestions:
        r = DataQualityRule(
            project_id=project_id, job_id=payload.get("job_id"),
            requirement_id=req_id, rule_type=s["rule_type"],
            definition_json=json.dumps(s["definition"], ensure_ascii=False),
            status="DRAFT", ai_generated=True, created_by=changed_by)
        db.add(r)
        out.append(r)
    await db.commit()
    for r in out:
        await db.refresh(r)
    return [ser_rule(r) for r in out]


@router.patch("/data-rules/{rule_id}", response_model=S.DataRuleResponse)
async def update_rule(rule_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(DataQualityRule).where(DataQualityRule.id == rule_id))).scalars().first()
    if not r:
        raise HTTPException(status_code=404, detail="Rule not found")
    if isinstance(payload.get("definition"), dict):
        if r.rule_type == "custom_sql":
            try:
                RE.validate_sql(payload["definition"].get("sql", ""))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        r.definition_json = json.dumps(payload["definition"], ensure_ascii=False)
    if payload.get("status") in ("DRAFT", "APPROVED", "REJECTED"):
        r.status = payload["status"]
    await db.commit()
    await db.refresh(r)
    return ser_rule(r)


@router.delete("/data-rules/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(DataQualityRule).where(DataQualityRule.id == rule_id))).scalars().first()
    if not r:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(r)
    await db.commit()
    return {"status": "deleted", "id": rule_id}


# ---------- Run / differences / report ----------
@router.post("/data-jobs/{job_id}/run")
async def run_job(job_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        return await RN.execute_job(
            db, job_id, (payload or {}).get("test_run_id"),
            (payload or {}).get("test_case_id"),
            (payload or {}).get("changed_by") or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/data-jobs/{job_id}/differences", response_model=List[S.DataDifferenceResponse])
async def list_differences(job_id: str, diff_type: Optional[str] = None,
                           severity: Optional[str] = None, status: Optional[str] = None,
                           limit: int = 200, db: AsyncSession = Depends(get_db)):
    await _get_job(db, job_id)
    stmt = select(DataDifference).where(
        DataDifference.job_id == job_id).order_by(DataDifference.created_at)
    if diff_type:
        stmt = stmt.where(DataDifference.diff_type == diff_type)
    if severity:
        stmt = stmt.where(DataDifference.severity == severity.upper())
    if status:
        stmt = stmt.where(DataDifference.status == status.upper())
    rows = (await db.execute(stmt.limit(min(max(limit, 1), 1000)))).scalars().all()
    return [ser_diff(d) for d in rows]


@router.post("/executions/{execution_id}/data-bug:draft")
async def draft_data_bug(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        return await RN.draft_data_bug(db, execution_id, (payload or {}).get("diff_ids"),
                                       (payload or {}).get("preferred_provider"),
                                       (payload or {}).get("model"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/data-differences/{diff_id}")
async def update_difference(diff_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    d = (await db.execute(select(DataDifference).where(DataDifference.id == diff_id))).scalars().first()
    if not d:
        raise HTTPException(status_code=404, detail="Difference not found")
    if payload.get("status") in ("OPEN", "BUG_FILED", "RESOLVED"):
        d.status = payload["status"]
    await db.commit()
    await db.refresh(d)
    return ser_diff(d)


@router.get("/data-jobs/{job_id}/report")
async def job_report(job_id: str, execution_id: Optional[str] = None,
                     db: AsyncSession = Depends(get_db)):
    await _get_job(db, job_id)
    try:
        return await RN.build_data_report(db, job_id, execution_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------- Data coverage (§55 + dashboard §62 inputs) ----------
@router.get("/data-coverage")
async def data_coverage(project_id: str, db: AsyncSession = Depends(get_db)):
    jobs = (await db.execute(select(DataQaJob).where(
        DataQaJob.project_id == project_id).order_by(desc(DataQaJob.created_at))
    )).scalars().all()
    out = []
    for j in jobs:
        diffs = (await db.execute(select(DataDifference.diff_type,
                                         func.count(DataDifference.id)).where(
            DataDifference.job_id == j.id).group_by(DataDifference.diff_type))).all()
        by_type = {k: v for k, v in diffs}
        rules_total = (await db.execute(select(func.count(DataQualityRule.id)).where(
            DataQualityRule.job_id == j.id))).scalar() or 0
        rules_ok = (await db.execute(select(func.count(DataQualityRule.id)).where(
            DataQualityRule.job_id == j.id,
            DataQualityRule.status == "APPROVED"))).scalar() or 0
        open_issues = (await db.execute(select(func.count(DataDifference.id)).where(
            DataDifference.job_id == j.id,
            DataDifference.status == "OPEN"))).scalar() or 0
        snaps = (await db.execute(select(DataSnapshot).where(
            DataSnapshot.job_id == j.id))).scalars().all()
        records = sum(s.row_count for s in snaps if s.side == "source")
        out.append({"job_id": j.id, "job_code": j.job_code, "name": j.name,
                    "status": j.status, "records_checked": records,
                    "fields_checked": None, "rules_checked": f"{rules_ok}/{rules_total}",
                    "differences": by_type, "open_issues": open_issues,
                    "build": j.build, "environment": j.environment})
    return out


@router.get("/data-overview")
async def data_overview(project_id: str, db: AsyncSession = Depends(get_db)):
    jobs = (await db.execute(select(func.count(DataQaJob.id)).where(
        DataQaJob.project_id == project_id))).scalar() or 0
    job_ids = (await db.execute(select(DataQaJob.id).where(
        DataQaJob.project_id == project_id))).scalars().all()
    compared = missing = extra = violations = failures = 0
    recent: list = []
    if job_ids:
        compared = (await db.execute(select(func.coalesce(func.sum(DataSnapshot.row_count), 0)).where(
            DataSnapshot.job_id.in_(job_ids), DataSnapshot.side == "source"))).scalar() or 0
        by_type = (await db.execute(select(DataDifference.diff_type,
                                           func.count(DataDifference.id)).where(
            DataDifference.job_id.in_(job_ids),
            DataDifference.status == "OPEN").group_by(DataDifference.diff_type))).all()
        by_sev = {k: v for k, v in by_type}
        missing = by_sev.get("missing", 0)
        extra = by_sev.get("extra", 0)
        violations = by_sev.get("rule_violation", 0) + by_sev.get("mismatch", 0)
        failures = (await db.execute(select(func.count(DataQaJob.id)).where(
            DataQaJob.project_id == project_id,
            DataQaJob.status == "FAILED"))).scalar() or 0
        rows = (await db.execute(select(DataDifference).where(
            DataDifference.job_id.in_(job_ids),
            DataDifference.status == "OPEN",
            DataDifference.severity.in_(["CRITICAL", "HIGH"])).order_by(
            desc(DataDifference.created_at)).limit(10))).scalars().all()
        recent = [{"id": d.id, "job_id": d.job_id, "diff_type": d.diff_type,
                   "biz_key": d.biz_key, "field": d.field,
                   "severity": d.severity} for d in rows]
    return {"jobs": jobs, "records_compared": compared, "differences": missing + extra + violations,
            "rule_violations": violations, "missing_records": missing,
            "failures": failures, "recent_issues": recent}
