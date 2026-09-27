"""Data QA job runner: snapshots, deterministic comparison, rules, differences,
TestExecution integration, evidence, bug drafts, bilingual reports.

Deterministic first; AI only explains/categorizes. Never modifies source data.
"""
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DATA_DIR
from app.core.logging import logger
from app.intelligence.models import WorkItem
from app.qa.models import TestCase
from app.qa.data_models import (
    DataSource, DataQaJob, FieldMapping, DataQualityRule, DataSnapshot,
    DataDifference,
)
from app.qa.execution_models import TestRun, TestExecution, TestEvidence
from app.qa import execution_engines as X
from app.qa import engines as E1
from app.qa.api_testing import redact as R
from app.qa.data_qa import readers, comparison as C, rules_engine as RE

DATA_QA_DIR = Path(DATA_DIR) / "data_qa"
DATA_QA_DIR.mkdir(parents=True, exist_ok=True)
MAX_STORED_DIFFS = 5_000
MAX_EVIDENCE_ROWS = 500


def _jl(text: str, default):
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


async def next_job_code(db: AsyncSession, project_id: str) -> str:
    import re as _re
    res = await db.execute(select(DataQaJob.job_code).where(
        DataQaJob.project_id == project_id))
    max_n = 0
    for (code,) in res.all():
        m = _re.search(r"(\d+)$", code or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"JOB-{max_n + 1:02d}"


def _source_rows(source: DataSource, row_cap: int) -> Tuple[List[str], List[Tuple[Dict[str, Any], int]], List[str]]:
    cfg = _jl(source.config_json, {})
    kind = source.kind
    if kind == "file_csv":
        fields, it = readers.read_csv(cfg.get("file_path", ""), cfg.get("encoding"),
                                      cfg.get("delimiter"), row_cap)
        return fields, readers.collect_rows(it, row_cap), []
    if kind == "file_excel":
        fields, warnings, it = readers.read_excel(cfg.get("file_path", ""),
                                                  cfg.get("sheet"), row_cap)
        return fields, readers.collect_rows(it, row_cap), warnings
    if kind in ("file_json", "api_result", "snapshot"):
        fields, it = readers.read_json_records(cfg.get("file_path", ""),
                                               cfg.get("json_path", ""), row_cap)
        return fields, readers.collect_rows(it, row_cap), []
    if kind == "manual_table":
        rows = cfg.get("rows") or []
        fields = list((cfg.get("fields") or [])) or (
            list(rows[0].keys()) if rows and isinstance(rows[0], dict) else [])
        return fields, [(r, i + 1) for i, r in enumerate(rows[:row_cap]) if isinstance(r, dict)], []
    raise ValueError(f"Unsupported source kind: {kind}")


def _write_snapshot_csv(job_id: str, side: str,
                        rows: List[Tuple[Dict[str, Any], int]]) -> Tuple[str, int, str]:
    fields: List[str] = []
    for row, _ in rows:
        for k in row.keys():
            if k not in fields:
                fields.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for row, _ in rows:
        w.writerow({f: ("" if row.get(f) is None else row.get(f)) for f in fields})
    data = buf.getvalue().encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    rel = f"{job_id}/{side}_{digest[:12]}.csv"
    path = DATA_QA_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel, len(rows), digest


async def execute_job(
    db: AsyncSession, job_id: str, test_run_id: Optional[str] = None,
    test_case_id: Optional[str] = None, changed_by: str = "user",
) -> Dict[str, Any]:
    job = (await db.execute(select(DataQaJob).where(DataQaJob.id == job_id))).scalars().first()
    if not job:
        raise ValueError("Job not found")
    src = (await db.execute(select(DataSource).where(DataSource.id == job.source_id))).scalars().first()
    dst = (await db.execute(select(DataSource).where(DataSource.id == job.dest_id))).scalars().first()
    if not src or not dst:
        raise ValueError("Job source/destination is not configured.")
    settings = _jl(job.settings_json, {})
    row_cap = int(settings.get("row_cap") or readers.DEFAULT_ROW_CAP)
    key_fields = _jl(job.key_fields_json, [])
    if not key_fields:
        raise ValueError("Business key is not defined for this job.")

    job.status = "RUNNING"
    await db.flush()
    warnings: List[str] = []
    try:
        src_fields, src_rows, src_warn = _source_rows(src, row_cap)
        dst_fields, dst_rows, dst_warn = _source_rows(dst, row_cap)
        warnings.extend(src_warn + dst_warn)

        # snapshots (file + metadata)
        for old in (await db.execute(select(DataSnapshot).where(
                DataSnapshot.job_id == job.id))).scalars().all():
            await db.delete(old)
        await db.flush()
        snapshots = []
        for side, rows in (("source", src_rows), ("dest", dst_rows)):
            rel, n, digest = _write_snapshot_csv(job.id, side, rows)
            snapshots.append(DataSnapshot(job_id=job.id, side=side,
                                          file_path=rel, row_count=n, content_hash=digest))
            db.add(snapshots[-1])

        mappings = (await db.execute(select(FieldMapping).where(
            FieldMapping.job_id == job.id))).scalars().all()
        map_list = [{"source_field": m.source_field, "dest_field": m.dest_field or m.source_field,
                     "transform_json": m.transform_json, "ignored": m.ignored,
                     "status": m.status} for m in mappings]
        unreviewed = any(m["status"] != "APPROVED" and not m["ignored"] for m in map_list)
        if unreviewed:
            warnings.append("unreviewed_mapping: some mappings are still DRAFT")

        src_index, src_dups = C.index_by_key(src_rows, key_fields)
        dst_index, dst_dups = C.index_by_key(dst_rows, key_fields)
        counts = C.compare_counts(len(src_rows), len(dst_rows))
        missing_keys, extra_keys = C.find_missing_extra(src_index, dst_index)

        diffs: List[Dict[str, Any]] = []
        sev_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

        def _push(dtype: str, biz_key: str, field: Optional[str],
                  expected: Any, actual: Any, rule_id: Optional[str] = None,
                  evidence: Optional[Dict[str, Any]] = None):
            sev, reason = C.severity_for(dtype, field or "", job.name)
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
            diffs.append({"diff_type": dtype, "biz_key": biz_key[:500], "field": field,
                          "expected": expected, "actual": actual,
                          "severity": sev, "severity_reason": reason,
                          "rule_id": rule_id, "evidence": evidence or {}})

        for k in missing_keys:
            _push("missing", k, None, "Exists in source", "Missing in destination")
        for k in extra_keys:
            _push("extra", k, None, "Absent in source", "Unexpected in destination")
        for k, c in C.detect_duplicates(src_index, src_dups):
            _push("duplicate", k, None, "1 record", f"{c} records in source")
        for k, c in C.detect_duplicates(dst_index, dst_dups):
            _push("duplicate", k, None, "1 record", f"{c} records in destination")

        # possible duplicates via configured combo
        combo = settings.get("possible_dup_fields") or []
        if combo:
            for row, no in src_rows:
                row["__biz_key__"] = make_biz(row, key_fields)
            for row, no in dst_rows:
                row["__biz_key__"] = make_biz(row, key_fields)
            for d in C.detect_possible_duplicates(src_rows + dst_rows, combo):
                _push("duplicate", d["key"], None, "unique business record",
                      f"possible duplicate ({d.get('combo', '')})")

        # field-level + encoding on matched keys
        matched = 0
        for k in src_index:
            if k not in dst_index:
                continue
            matched += 1
            srow, _ = src_index[k]
            drow, _ = dst_index[k]
            for mm in C.compare_fields(srow, drow, map_list):
                _push("mismatch", k, mm["field"], mm["expected"], mm["actual"])
            for f, v in list(srow.items())[:50]:
                enc = C.check_encoding(v, f)
                if enc:
                    _push("encoding", k, f, "clean text",
                          f"{','.join(enc['issues'])}: {enc['sample']}")

        # approved rules
        rules = (await db.execute(select(DataQualityRule).where(
            DataQualityRule.job_id == job.id,
            DataQualityRule.status == "APPROVED"))).scalars().all()
        violations = 0
        for rule in rules:
            definition = _jl(rule.definition_json, {})
            rtype = rule.rule_type
            if rtype in ("required", "range", "format", "cross_field", "consistency"):
                for side_rows in (src_rows, dst_rows):
                    for row, no in side_rows:
                        v = RE.eval_rule_on_row(rtype, definition, row)
                        if v:
                            violations += 1
                            _push("rule_violation", make_biz(row, key_fields),
                                  v.get("field"), "rule satisfied",
                                  f"{v.get('issue')}: {v.get('value', '')}",
                                  rule_id=rule.id)
            elif rtype == "unique":
                fields = definition.get("fields") or ([definition.get("field")] if definition.get("field") else [])
                for side_rows, side in ((src_rows, "source"), (dst_rows, "dest")):
                    for v in RE.eval_unique(side_rows, fields):
                        violations += 1
                        _push("rule_violation", v["key"], ",".join(fields),
                              "unique", f"duplicate in {side} (rows {v.get('first_row_no')}/{v.get('row_no')})",
                              rule_id=rule.id)
            elif rtype == "calculation":
                calc_side = (definition.get("side") or "dest").lower()
                target_rows = [r for r, _ in (dst_rows if calc_side == "dest" else src_rows)]
                details = definition.get("details") or {}
                for v in RE.eval_calculation(target_rows, target_rows, definition):
                    violations += 1
                    _push("rule_violation", v.get("key", ""), definition.get("header_field"),
                          f"sum={v.get('expected')}", f"sum={v.get('actual')}",
                          rule_id=rule.id)
            elif rtype == "ref_integrity":
                child_f, parent_f = definition.get("child_field"), definition.get("parent_field")
                parent_vals = {str(r.get(parent_f)) for r, _ in dst_rows}
                for row, no in src_rows:
                    if str(row.get(child_f)) not in parent_vals:
                        violations += 1
                        _push("rule_violation", make_biz(row, key_fields), child_f,
                              f"exists in {parent_f}", "orphan (parent missing)",
                              rule_id=rule.id)
            elif rtype == "custom_sql":
                side = (definition.get("side") or "dest").lower()
                target = [r for r, _ in (dst_rows if side == "dest" else src_rows)]
                try:
                    bad_rows = RE.run_guarded_sql(target, definition.get("sql", ""))
                    for br in bad_rows:
                        violations += 1
                        _push("rule_violation", str(br.get(key_fields[0], "")) if key_fields else "",
                              ",".join(key_fields), "rule satisfied",
                              f"custom SQL flagged: {json_dumps_short(br)}",
                              rule_id=rule.id)
                except ValueError as se:
                    warnings.append(f"custom_sql rejected: {se}")

        # persist differences (cap) + aggregate rest
        for old in (await db.execute(select(DataDifference).where(
                DataDifference.job_id == job.id))).scalars().all():
            await db.delete(old)
        await db.flush()
        stored = 0
        stored_rows: list = []
        for d in diffs:
            if stored >= MAX_STORED_DIFFS:
                break
            row = DataDifference(
                job_id=job.id, diff_type=d["diff_type"], biz_key=d["biz_key"],
                field=d.get("field"),
                expected=str(d.get("expected"))[:2000] if d.get("expected") is not None else None,
                actual=str(d.get("actual"))[:2000] if d.get("actual") is not None else None,
                severity=d["severity"], severity_reason=d.get("severity_reason"),
                rule_id=d.get("rule_id"), evidence_json=json.dumps(d.get("evidence") or {}, ensure_ascii=False))
            db.add(row)
            stored_rows.append(row)
            stored += 1
        await db.flush()

        by_type: Dict[str, int] = {}
        for d in diffs:
            by_type[d["diff_type"]] = by_type.get(d["diff_type"], 0) + 1
        summary = {
            "compared": len(src_rows), "dest_rows": len(dst_rows),
            "count_diff": counts["diff"], "matched": matched,
            "missing": len(missing_keys), "extra": len(extra_keys),
            "mismatch": by_type.get("mismatch", 0),
            "rule_violations": violations,
            "duplicates": by_type.get("duplicate", 0),
            "encoding": by_type.get("encoding", 0),
            "by_severity": sev_counts, "stored_differences": stored,
            "total_differences": len(diffs), "warnings": warnings,
        }
        failed = len(diffs) > 0
        status = "FAIL" if failed else "PASS"
        job.status = "COMPLETED"
        await db.flush()

        # TestExecution integration (§58-60)
        run_id = test_run_id
        if not run_id:
            run = TestRun(project_id=job.project_id,
                          run_code=await X.next_run_code(db, job.project_id),
                          name=f"Ad-hoc DATA {datetime.datetime.utcnow().strftime('%Y/%m/%d %H:%M')}",
                          version_build=job.build, environment=job.environment,
                          scope_json=json.dumps({"adhoc": True, "type": "DATA",
                                                 "job_id": job.id}, ensure_ascii=False))
            db.add(run)
            await db.flush()
            run_id = run.id
        tc_id = test_case_id
        if not tc_id:
            tc = TestCase(
                project_id=job.project_id, tc_code=await _next_tc_code(db, job.project_id),
                title=f"DATA QA: {job.name}"[:255],
                purpose=f"Automated data validation for job {job.job_code}",
                case_type="Validation", priority="HIGH",
                expected_result="No differences, all rules satisfied",
                requirement_id=job.requirement_id or (await _fallback_req(db, job)),
                evidence_quote=f"Data QA job {job.job_code}",
                knowledge_class="Confirmed", source="Manual",
                ai_generated=False, confidence=1.0, status="APPROVED")
            db.add(tc)
            await db.flush()
            tc_id = tc.id
        actual_text = json.dumps(summary, ensure_ascii=False)[:4000]
        ex = TestExecution(
            test_run_id=run_id, test_case_id=tc_id,
            requirement_id=(await db.execute(select(TestCase.requirement_id).where(
                TestCase.id == tc_id))).scalar(),
            attempt_no=1, status=status, actual_result=actual_text,
            fail_reason=(f"{len(diffs)} difference(s): " +
                         ", ".join(f"{k}={v}" for k, v in by_type.items()))[:1000] if failed else None,
            tester=changed_by, executed_at=datetime.datetime.utcnow(),
            case_snapshot_json=json.dumps({"job_id": job.id, "job_code": job.job_code,
                                           "summary": summary}, ensure_ascii=False))
        db.add(ex)
        await db.flush()
        for row in stored_rows:
            row.execution_id = ex.id
        await db.flush()
        await X.log_history(db, ex.id, "status", "NOT_RUN", status, changed_by)
        for d in diffs[:MAX_EVIDENCE_ROWS]:
            db.add(TestEvidence(
                execution_id=ex.id, test_case_id=tc_id,
                requirement_id=ex.requirement_id,
                evidence_type="note", title=f"[{d['diff_type']}] {d['biz_key']}"[:255],
                text_content=json.dumps(R.redact_json({
                    "field": d.get("field"), "expected": d.get("expected"),
                    "actual": d.get("actual"), "severity": d["severity"],
                    "reason": d.get("severity_reason")}), ensure_ascii=False)[:2000],
                created_by=changed_by))
        await db.flush()
        await X.refresh_exec_coverage(db, ex.requirement_id)
        await db.commit()
        return {"job_id": job.id, "job_code": job.job_code, "status": status,
                "summary": summary, "execution_id": ex.id,
                "test_run_id": run_id, "test_case_id": tc_id}
    except Exception as e:
        logger.warning(f"Data QA job {job_id} failed: {e}")
        try:
            job.status = "FAILED"
            await db.commit()
        except Exception:
            pass
        raise


def make_biz(row: Dict[str, Any], key_fields: List[str]) -> str:
    return C.make_key(row, key_fields)[:500]


def json_dumps_short(obj: Any, limit: int = 300) -> str:
    try:
        return json.dumps(R.redact_json(obj), ensure_ascii=False, default=str)[:limit]
    except Exception:
        return str(obj)[:limit]


async def _next_tc_code(db: AsyncSession, project_id: str) -> str:
    import re as _re
    res = await db.execute(select(TestCase.tc_code).where(TestCase.project_id == project_id))
    max_n = 0
    for (code,) in res.all():
        m = _re.search(r"(\d+)$", code or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"TC-DATA-{max_n + 1:03d}"


async def _fallback_req(db: AsyncSession, job: DataQaJob) -> str:
    req = (await db.execute(select(WorkItem).where(
        WorkItem.project_id == job.project_id,
        WorkItem.item_type == "REQUIREMENT").order_by(WorkItem.created_at).limit(1)
    )).scalars().first()
    if not req:
        raise ValueError("Project has no requirement to attach the DATA test case.")
    return req.id


async def draft_data_bug(db: AsyncSession, execution_id: str,
                         diff_ids: Optional[List[str]] = None,
                         preferred_provider: Optional[str] = None,
                         model: Optional[str] = None) -> Dict[str, Any]:
    """AI-assisted JA/VI bug draft from data differences. Evidence-first, masked."""
    from sqlalchemy import select as _select
    ex = await X.get_execution(db, execution_id)
    if not ex:
        raise ValueError("Execution not found")
    stmt = _select(DataDifference).where(DataDifference.execution_id == execution_id)
    if diff_ids:
        stmt = stmt.where(DataDifference.id.in_(diff_ids))
    diffs = (await db.execute(stmt.limit(20))).scalars().all()
    if not diffs:
        raise ValueError("No differences to report.")
    tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
    req = await E1.get_requirement(db, ex.requirement_id)
    run = (await db.execute(select(TestRun).where(TestRun.id == ex.test_run_id))).scalars().first()
    items = [{"key": d.biz_key, "type": d.diff_type, "field": d.field,
              "expected": (d.expected or "")[:200], "actual": (d.actual or "")[:200],
              "severity": d.severity} for d in diffs]
    clean_items, _ = R.redact_for_ai({"differences": items})
    from app.qa.llm import generate_qa_json
    prompt = f"""Write a neutral data-QA bug report in Japanese and Vietnamese from these facts only.
Test: {tc.tc_code if tc else ''} {tc.title if tc else ''}
Requirement: {req.title if req else ''} | Build: {run.version_build if run else ''} | Env: {run.environment if run else ''}
Differences (masked): {json.dumps(clean_items, ensure_ascii=False)[:2500]}
Structure JA: 【不具合概要】【対象データ】【環境】【確認条件】【期待結果】【実際結果】【差分】【対象件数】【備考】.
Never blame, never guess root cause, never paste raw sensitive data.
Return strict JSON: {{"title_ja": "...", "title_vi": "...", "summary_ja": "...", "summary_vi": "...",
"target_data_ja": "...", "conditions_ja": "...", "expected_ja": "...", "actual_ja": "...",
"affected_count": "...", "notes_ja": "...", "severity_suggestion": "CRITICAL|HIGH|MEDIUM|LOW"}}"""
    parsed = await generate_qa_json(
        prompt, "You are a senior QA engineer writing neutral bilingual data bug reports.",
        preferred_provider, model, max_tokens=1500)
    if not isinstance(parsed, dict) or not parsed:
        first = diffs[0]
        parsed = {"title_ja": f"【不具合】データ差分 {len(diffs)}件",
                  "title_vi": f"Lệch dữ liệu: {len(diffs)} điểm",
                  "summary_ja": f"{first.diff_type}: {first.biz_key[:100]}",
                  "summary_vi": f"{first.diff_type}: {first.biz_key[:100]}",
                  "target_data_ja": "", "conditions_ja": "",
                  "expected_ja": first.expected or "", "actual_ja": first.actual or "",
                  "affected_count": str(len(diffs)), "notes_ja": "",
                  "severity_suggestion": first.severity}
    parsed["execution_id"] = execution_id
    parsed["diff_ids"] = [d.id for d in diffs]
    parsed["requirement_id"] = ex.requirement_id
    parsed["test_case_id"] = ex.test_case_id
    return parsed


async def build_data_report(db: AsyncSession, job_id: str, execution_id: Optional[str] = None,
                            preferred_provider: Optional[str] = None,
                            model: Optional[str] = None) -> Dict[str, str]:
    """Factual JA/VI report: what was checked and found. Never claims absolute correctness."""
    job = (await db.execute(select(DataQaJob).where(DataQaJob.id == job_id))).scalars().first()
    if not job:
        raise ValueError("Job not found")
    ex = None
    if execution_id:
        ex = await X.get_execution(db, execution_id)
    summary = _jl((ex.actual_result if ex else None) or "{}", {})
    facts = {"job": job.name, "job_code": job.job_code, "build": job.build,
             "environment": job.environment, "summary": summary}
    from app.qa.llm import generate_qa_json
    prompt = f"""Write a factual data-QA report (Japanese + Vietnamese) from these facts only:
{json.dumps(facts, ensure_ascii=False)[:2500]}
Sections: Scope, Source, Destination, Environment, Records Compared, Matched, Missing, Extra, Mismatch, Rule Violations, Open Issues, Known Limitations.
State counts only. NEVER say migration/data is fully correct.
Return strict JSON: {{"markdown_vi": "...", "markdown_ja": "..."}}"""
    parsed = await generate_qa_json(
        prompt, "You are a senior QA lead writing factual bilingual data-QA reports.",
        preferred_provider, model, max_tokens=2000)
    if not isinstance(parsed, dict) or not parsed.get("markdown_vi"):
        s = summary
        vi = (f"# Data QA Report — {job.name} ({job.job_code})\n\n"
              f"- Build: {job.build} | Env: {job.environment}\n"
              f"- Compared: {s.get('compared', 0)} | Matched: {s.get('matched', 0)}\n"
              f"- Missing: {s.get('missing', 0)} | Extra: {s.get('extra', 0)} | "
              f"Mismatch: {s.get('mismatch', 0)} | Rule violations: {s.get('rule_violations', 0)}\n")
        ja = (f"# データQAレポート — {job.name} ({job.job_code})\n\n"
              f"- ビルド: {job.build} | 環境: {job.environment}\n"
              f"- 比較件数: {s.get('compared', 0)} | 一致: {s.get('matched', 0)}\n"
              f"- 不足: {s.get('missing', 0)} | 余分: {s.get('extra', 0)} | "
              f"不一致: {s.get('mismatch', 0)} | ルール違反: {s.get('rule_violations', 0)}\n")
        return {"markdown_vi": vi, "markdown_ja": ja}
    return {"markdown_vi": parsed.get("markdown_vi", ""),
            "markdown_ja": parsed.get("markdown_ja", "")}
