import json
from typing import Dict, Any, List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.intelligence.models import MeetingRecord, WorkItem, WorkItemEvidence
from app.documents.models import DocumentFile
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

async def extract_meeting_intelligence_dynamic(
    db: AsyncSession,
    m: MeetingRecord,
    provider_name: str = "groq",
    model: Optional[str] = None
) -> Dict[str, int]:
    """Dynamically analyzes meeting content using AI (Groq/Gemini fallback)
    to extract Requirements and Bugs with direct meeting quotes as evidence.
    Zero hardcoded project IDs or meeting titles.
    """
    # 1. Check if requirements/bugs already extracted for this meeting
    existing_items = (await db.execute(
        select(WorkItem.item_type)
        .join(WorkItemEvidence, WorkItem.id == WorkItemEvidence.work_item_id)
        .where(
            WorkItemEvidence.source_type == "meeting",
            WorkItemEvidence.source_id == m.id,
            WorkItem.item_type.in_(["REQUIREMENT", "BUG"])
        )
    )).scalars().all()

    if existing_items:
        # Already extracted previously, skip redundant AI calls to protect quota
        return {"requirements": 0, "bugs": 0}

    # 2. Extract content from summary_markdown and transcript
    content_text = ""
    if m.summary_markdown:
        try:
            s_obj = json.loads(m.summary_markdown)
            if isinstance(s_obj, dict):
                content_text = f"Tiếng Việt: {s_obj.get('vi', '')}\nTiếng Nhật: {s_obj.get('ja', '')}"
            else:
                content_text = str(m.summary_markdown)
        except Exception:
            content_text = str(m.summary_markdown)

    if len(content_text.strip()) < 100 and m.transcript_text:
        content_text += f"\nTrích dẫn biên bản họp:\n{m.transcript_text[:2500]}"

    if not content_text.strip():
        return {"requirements": 0, "bugs": 0}

    # 3. Dynamic AI Prompt for BrSE Requirements & Bug extraction
    prompt = f"""Bạn là một kỹ sư cầu nối BrSE (Bridge Software Engineer) chuyên nghiệp.
Hãy đọc nội dung cuộc họp sau đây và trích xuất:
1. Các YÊU CẦU KỸ THUẬT / TÍNH NĂNG (REQUIREMENTS) được khách hàng yêu cầu hoặc các bên đã thống nhất.
2. Các LỖI PHẦN MỀM / VẤN ĐỀ HIỆU NĂNG / RỦI RO KỸ THUẬT (BUGS) được báo cáo hoặc cần xử lý.

Thông tin cuộc họp:
- Tiêu đề: {m.title}
- Ngày họp: {m.meeting_date}
- Nội dung cuộc họp:
{content_text[:3500]}

YÊU CẦU ĐỊNH DẠNG ĐẦU RA (Strict JSON format only):
{{
  "requirements": [
    {{
      "title": "Tiêu đề ngắn gọn của yêu cầu chức năng/kỹ thuật",
      "description": "Mô tả chi tiết giải pháp, trường dữ liệu, hoặc logic cần thực hiện",
      "priority": "CRITICAL / HIGH / MEDIUM",
      "assignee": "Dev Team hoặc vai trò phụ trách",
      "quote": "Câu trích dẫn ngắn bằng tiếng Nhật hoặc tiếng Việt trong nội dung họp làm bằng chứng"
    }}
  ],
  "bugs": [
    {{
      "title": "Tiêu đề lỗi phần mềm, hiệu năng hoặc rủi ro kỹ thuật",
      "description": "Mô tả hiện tượng lỗi, nguyên nhân hoặc rủi ro mất an toàn dữ liệu",
      "priority": "CRITICAL / HIGH / MEDIUM",
      "assignee": "Dev Team hoặc vai trò phụ trách",
      "quote": "Câu trích dẫn ngắn bằng tiếng Nhật hoặc tiếng Việt trong nội dung họp làm bằng chứng"
    }}
  ]
}}
Chỉ trả về duy nhất khối JSON hợp lệ, không kèm lời giải thích râu ria."""

    provider_chain = [provider_name, "gemini", "groq"] if provider_name not in ["auto", None] else ["groq", "gemini"]
    parsed = None

    for prov_c in provider_chain:
        p = provider_registry.get_provider(prov_c)
        if not p:
            continue
        try:
            t_model = model if (prov_c == provider_name and model) else None
            resp = await p.generate(
                prompt=prompt,
                system_instruction="You are an expert BrSE Lead analyzing meeting minutes to extract requirements and bugs.",
                model=t_model,
                temperature=0.1,
                json_mode=True
            )
            if resp and resp.text:
                parsed = clean_json_response(resp.text)
                if isinstance(parsed, dict) and ("requirements" in parsed or "bugs" in parsed):
                    break
        except Exception as e:
            logger.warning(f"Dynamic meeting extraction with {prov_c} failed: {e}")

    if not parsed or not isinstance(parsed, dict):
        return {"requirements": 0, "bugs": 0}

    req_count = 0
    bug_count = 0

    # 4. Save extracted Requirements
    for req in parsed.get("requirements", []):
        title = (req.get("title") or "").strip()
        if not title:
            continue
        desc = req.get("description") or title
        quote = (req.get("quote") or title).strip()

        wi = WorkItem(
            project_id=m.project_id,
            item_type="REQUIREMENT",
            title=title,
            description=desc,
            status="CONFIRMED",
            priority=req.get("priority") or "HIGH",
            confidence=0.95,
            assignee=req.get("assignee") or "Dev Team",
            deadline_date=None
        )
        db.add(wi)
        await db.flush()

        db.add(WorkItemEvidence(
            work_item_id=wi.id,
            source_type="meeting",
            source_id=m.id,
            quote_text=quote,
            author=f"Cuộc họp {m.meeting_date}",
            timestamp=m.meeting_date,
            confirmation_status="CONFIRMED"
        ))
        req_count += 1

    # 5. Save extracted Bugs
    for bg in parsed.get("bugs", []):
        title = (bg.get("title") or "").strip()
        if not title:
            continue
        desc = bg.get("description") or title
        quote = (bg.get("quote") or title).strip()

        wi = WorkItem(
            project_id=m.project_id,
            item_type="BUG",
            title=title,
            description=desc,
            status="CONFIRMED",
            priority=bg.get("priority") or "HIGH",
            confidence=0.95,
            assignee=bg.get("assignee") or "Dev Team",
            deadline_date=None
        )
        db.add(wi)
        await db.flush()

        db.add(WorkItemEvidence(
            work_item_id=wi.id,
            source_type="meeting",
            source_id=m.id,
            quote_text=quote,
            author=f"Cuộc họp {m.meeting_date}",
            timestamp=m.meeting_date,
            confirmation_status="CONFIRMED"
        ))
        bug_count += 1

    await db.commit()
    logger.info(f"[AI_EXTRACTOR] Meeting '{m.title}' dynamically extracted {req_count} requirements and {bug_count} bugs.")
    return {"requirements": req_count, "bugs": bug_count}

async def sync_single_meeting_to_work_items(db: AsyncSession, m: MeetingRecord) -> Dict[str, int]:
    """Synchronizes decisions, open questions, action items, and dynamically extracts
    requirements and bugs for any MeetingRecord without hardcoded data.
    """
    existing_evs = (await db.execute(
        select(WorkItemEvidence).where(
            WorkItemEvidence.source_type == "meeting",
            WorkItemEvidence.source_id == m.id
        )
    )).scalars().all()
    evidence_lookup = {e.quote_text.strip(): True for e in existing_evs}

    created_counts = {"decisions": 0, "questions": 0, "deadlines": 0, "requirements": 0, "bugs": 0}

    # Decisions
    try:
        decs = json.loads(m.decisions_json or "[]")
    except Exception:
        decs = []
    for d in decs:
        t_vi = d.get("title_vi") or d.get("title") or d.get("title_ja") or f"Quyết định kỹ thuật ngày {m.meeting_date}"
        t_vi = t_vi.strip()
        det_vi = d.get("detail_vi") or d.get("detail") or d.get("reason_vi") or d.get("reason") or ""
        quote = d.get("title_ja") or d.get("reason_vi") or t_vi
        quote = quote.strip()
        if quote in evidence_lookup or t_vi in evidence_lookup:
            continue

        wi = WorkItem(
            project_id=m.project_id,
            item_type="DECISION",
            title=t_vi,
            description=det_vi,
            status="CONFIRMED",
            priority="HIGH",
            confidence=0.98,
            assignee="Hội đồng cuộc họp",
            deadline_date=None
        )
        db.add(wi)
        await db.flush()
        db.add(WorkItemEvidence(
            work_item_id=wi.id,
            source_type="meeting",
            source_id=m.id,
            quote_text=quote,
            author=f"Cuộc họp {m.meeting_date}",
            timestamp=m.meeting_date,
            confirmation_status="CONFIRMED"
        ))
        evidence_lookup[quote] = True
        created_counts["decisions"] += 1

    # Questions
    try:
        qs = json.loads(m.open_questions_json or "[]")
    except Exception:
        qs = []
    for q in qs:
        q_title = q.get("question_vi") or q.get("question") or q.get("question_ja") or f"Câu hỏi tồn đọng ngày {m.meeting_date}"
        q_title = q_title.strip()
        q_detail = q.get("question_ja") or q.get("context") or ""
        quote = q.get("question_ja") or q_title
        quote = quote.strip()
        if quote in evidence_lookup or q_title in evidence_lookup:
            continue

        wi = WorkItem(
            project_id=m.project_id,
            item_type="OPEN_QUESTION",
            title=q_title,
            description=q_detail,
            status="PROPOSED",
            priority="HIGH",
            confidence=0.92,
            assignee=q.get("assigned_to") or "Khách hàng Nhật",
            deadline_date=None
        )
        db.add(wi)
        await db.flush()
        db.add(WorkItemEvidence(
            work_item_id=wi.id,
            source_type="meeting",
            source_id=m.id,
            quote_text=quote,
            author=f"Cuộc họp {m.meeting_date}",
            timestamp=m.meeting_date,
            confirmation_status="PROPOSED"
        ))
        evidence_lookup[quote] = True
        created_counts["questions"] += 1

    # Action Items
    try:
        acts = json.loads(m.action_items_json or "[]")
    except Exception:
        acts = []
    for a in acts:
        t_title = a.get("task_vi") or a.get("task") or a.get("task_ja") or f"Hạng mục công việc ngày {m.meeting_date}"
        t_title = t_title.strip()
        t_desc = a.get("task_ja") or a.get("task_vi_detail") or a.get("task_vi") or ""
        quote = a.get("task_ja") or t_title
        quote = quote.strip()
        if quote in evidence_lookup or t_title in evidence_lookup:
            continue

        due = a.get("due_date")
        if due in ["Chưa xác định", "None", "", None]:
            due = None

        wi = WorkItem(
            project_id=m.project_id,
            item_type="DEADLINE" if due else "TODO",
            title=t_title,
            description=t_desc,
            status="PROPOSED",
            priority=a.get("priority") or "HIGH",
            confidence=0.95,
            assignee=a.get("assignee") or "Dev Team",
            deadline_date=due
        )
        db.add(wi)
        await db.flush()
        db.add(WorkItemEvidence(
            work_item_id=wi.id,
            source_type="meeting",
            source_id=m.id,
            quote_text=quote,
            author=f"Cuộc họp {m.meeting_date}",
            timestamp=m.meeting_date,
            confirmation_status="PROPOSED"
        ))
        evidence_lookup[quote] = True
        created_counts["deadlines"] += 1

    await db.commit()

    # Dynamic AI Extraction of Requirements & Bugs
    ai_counts = await extract_meeting_intelligence_dynamic(db, m)
    created_counts["requirements"] = ai_counts["requirements"]
    created_counts["bugs"] = ai_counts["bugs"]

    return created_counts

async def cleanup_mock_data_and_sync(db: AsyncSession) -> Dict[str, Any]:
    """
    1. Purges all mock/test WorkItems that have 0 evidence items.
    2. Dynamically analyzes and migrates all MeetingRecords into real WorkItems
       (Decisions, Questions, Deadlines, and AI-extracted Requirements & Bugs).
    3. Triggers Document RAG Indexing on project documents into SQLite FTS5.
    Zero hardcoded values.
    """
    # 1. Delete mock items with 0 evidence
    all_items = (await db.execute(
        select(WorkItem).options(selectinload(WorkItem.evidence_items))
    )).scalars().all()

    mock_items_deleted = 0
    for item in all_items:
        if not item.evidence_items:
            await db.delete(item)
            mock_items_deleted += 1

    await db.flush()

    # 2. Iterate through all meetings in DB dynamically
    meetings = (await db.execute(select(MeetingRecord))).scalars().all()

    total_decs = 0
    total_qs = 0
    total_deadlines = 0
    total_reqs = 0
    total_bugs = 0

    for m in meetings:
        res = await sync_single_meeting_to_work_items(db, m)
        total_decs += res["decisions"]
        total_qs += res["questions"]
        total_deadlines += res["deadlines"]
        total_reqs += res["requirements"]
        total_bugs += res["bugs"]

    # 3. Index existing project documents into Project Document RAG
    rag_indexed_chunks = 0
    try:
        from app.intelligence.rag.project_rag_service import project_rag_service
        all_docs = (await db.execute(select(DocumentFile).where(DocumentFile.project_id != None))).scalars().all()
        for doc in all_docs:
            c = await project_rag_service.index_document_file(db, doc)
            rag_indexed_chunks += c
    except Exception as e:
        logger.warning(f"Initial document RAG indexing warning: {e}")

    logger.info(
        f"[SYNC_DYNAMIC] Processed {len(meetings)} meetings. "
        f"Migrated {total_decs} decisions, {total_qs} questions, {total_deadlines} deadlines, "
        f"{total_reqs} requirements, {total_bugs} bugs. "
        f"Indexed {rag_indexed_chunks} document chunks into RAG."
    )

    return {
        "status": "success",
        "mock_items_deleted": mock_items_deleted,
        "total_meetings_processed": len(meetings),
        "decisions_migrated": total_decs,
        "questions_migrated": total_qs,
        "deadlines_migrated": total_deadlines,
        "requirements_migrated": total_reqs,
        "bugs_migrated": total_bugs,
        "rag_chunks_indexed": rag_indexed_chunks
    }
