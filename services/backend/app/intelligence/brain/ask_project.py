import json
import re
from typing import Dict, List, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import WorkItem, WorkItemEvidence, MeetingRecord
from app.intelligence.rag.project_rag_service import project_rag_service

def extract_one_line_gist(summary_vi: str, decisions: list) -> str:
    """Extracts a concise 1-sentence gist for the timeline index."""
    if decisions:
        first_dec = decisions[0]
        title = first_dec.get("title_vi") or first_dec.get("title") or ""
        if title:
            return title[:120]
    lines = [l.strip().lstrip("-*# ") for l in summary_vi.split("\n") if l.strip()]
    if lines:
        return lines[0][:120]
    return "Trao đổi nghiệp vụ và kỹ thuật dự án."

def score_work_items_relevance(items: List[WorkItem], question: str) -> List[WorkItem]:
    """Sorts work items by keyword relevance to question."""
    q_words = set(re.findall(r"[\w\u00C0-\u024F\u1EA0-\u1EF9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,}", question.lower()))
    scored = []
    for it in items:
        sc = 1.0
        t_low = (it.title or "").lower()
        d_low = (it.description or "").lower()
        for w in q_words:
            if len(w) <= 2 and w not in ["ui", "db", "api", "kot"]:
                continue
            if w in t_low:
                sc += 4.0
            if w in d_low:
                sc += 2.0
        # Boost confirmed or in-progress items
        if it.status in ("CONFIRMED", "DONE"):
            sc += 1.5
        scored.append((it, sc))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [x[0] for x in scored]

class AskProjectEngine:
    """Full BrSE AI Copilot across Meetings, WorkItems, Requirements, Decisions, Evidence & Messages."""

    @classmethod
    async def ask_project(
        cls,
        db: AsyncSession,
        project_id: Optional[str],
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        scope: str = "all", # all, meetings, work_items, evidences
        provider_name: str = "groq",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Answers project questions with concrete source citations, known unknowns, and follow-up prompts."""
        effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None

        # 1. Fetch Meetings
        stmt_m = select(MeetingRecord)
        if effective_pid:
            stmt_m = stmt_m.where(MeetingRecord.project_id == effective_pid)
        stmt_m = stmt_m.order_by(MeetingRecord.meeting_date.asc())
        meetings = (await db.execute(stmt_m)).scalars().all()

        # 2. Fetch WorkItems
        stmt_w = select(WorkItem)
        if effective_pid:
            stmt_w = stmt_w.where(WorkItem.project_id == effective_pid)
        work_items_all = (await db.execute(stmt_w)).scalars().all()

        # 3. Fetch Evidence
        stmt_ev = select(WorkItemEvidence)
        if effective_pid:
            stmt_ev = stmt_ev.join(WorkItem, WorkItemEvidence.work_item_id == WorkItem.id).where(WorkItem.project_id == effective_pid)
        stmt_ev = stmt_ev.order_by(WorkItemEvidence.created_at.desc()).limit(25)
        evidences = (await db.execute(stmt_ev)).scalars().all()

        # Build Knowledge Blocks according to Scope
        knowledge_sections = []

        # --- A. MEETINGS KNOWLEDGE ---
        if scope in ("all", "meetings") and meetings:
            m_timeline = ["### [NGUỒN CUỘC HỌP] DÒNG THỜI GIAN VÀ CÁC MỐC HỌP (MEETINGS TIMELINE):"]
            for m in meetings:
                try:
                    decs = json.loads(m.decisions_json or "[]")
                except Exception:
                    decs = []
                summary_vi = m.summary_markdown or ""
                try:
                    s_obj = json.loads(m.summary_markdown)
                    if isinstance(s_obj, dict):
                        summary_vi = s_obj.get("vi", "") or m.summary_markdown or ""
                except Exception:
                    pass
                gist = extract_one_line_gist(summary_vi, decs)
                m_timeline.append(f"• [{m.meeting_date}] \"{m.title}\" (ID: {m.id}): {gist} [{len(decs)} quyết định]")

            # Add deep details for Top 4 relevant meetings
            q_lower = question.lower()
            scored_m = []
            for m in meetings:
                score = 1.0
                m_text = f"{m.title} {m.meeting_date} {m.summary_markdown}".lower()
                for w in re.findall(r"[\w\u00C0-\u024F\u1EA0-\u1EF9]{2,}", q_lower):
                    if w in m_text:
                        score += 3.0
                scored_m.append((m, score))
            scored_m.sort(key=lambda x: x[1], reverse=True)

            m_details = ["\nChi tiết các cuộc họp liên quan nhất:"]
            for m, sc in scored_m[:2]:
                try:
                    decs = json.loads(m.decisions_json or "[]")
                except Exception:
                    decs = []
                try:
                    acts = json.loads(m.action_items_json or "[]")
                except Exception:
                    acts = []
                summary_vi = m.summary_markdown or ""
                try:
                    s_obj = json.loads(m.summary_markdown)
                    if isinstance(s_obj, dict):
                        summary_vi = s_obj.get("vi", "") or m.summary_markdown or ""
                except Exception:
                    pass
                lines = [f"=== Cuộc họp: \"{m.title}\" ({m.meeting_date}) ==="]
                if summary_vi:
                    lines.append(f"Tóm tắt: {summary_vi[:250]}...")
                for d in decs[:3]:
                    t_d = d.get("title_vi") or d.get("title") or ""
                    dt_d = d.get("detail_vi") or d.get("detail") or ""
                    lines.append(f"  * [QUYẾT ĐỊNH] {t_d}: {dt_d[:120]}")
                for a in acts[:2]:
                    t_a = a.get("task_vi") or a.get("task") or ""
                    lines.append(f"  * [ACTION] {t_a} (Phụ trách: {a.get('assignee', 'N/A')}, Hạn: {a.get('due_date', 'N/A')})")
                m_details.append("\n".join(lines))

            knowledge_sections.append("\n".join(m_timeline) + "\n" + "\n\n".join(m_details))

        # --- B. WORK ITEMS KNOWLEDGE ---
        if scope in ("all", "work_items") and work_items_all:
            sorted_items = score_work_items_relevance(work_items_all, question)
            top_items = sorted_items[:10]

            w_lines = [f"### [NGUỒN WORK ITEMS & QUYẾT ĐỊNH] ({len(top_items)} mục liên quan nhất):"]
            for it in top_items:
                w_lines.append(
                    f"• [{it.item_type}] {it.title} | Trạng thái: {it.status} | Phụ trách: {it.assignee or 'N/A'} | Chi tiết: {it.description[:120]}"
                )
            knowledge_sections.append("\n".join(w_lines))

        # --- C. EVIDENCE QUOTES KNOWLEDGE ---
        if scope in ("all", "evidences") and evidences:
            ev_lines = ["### [NGUỒN BẰNG CHỨNG NGUYÊN VĂN (EVIDENCE QUOTES)] :"]
            for ev in evidences[:6]:
                ev_lines.append(
                    f"• [{ev.source_type.upper()}] ({ev.author or 'Team'}, {ev.timestamp or 'Gần đây'}): \"{ev.quote_text[:150]}\""
                )
            knowledge_sections.append("\n".join(ev_lines))

        # --- D. PROJECT DOCUMENTS RAG (TOKEN-SAFE CHUNKS ACROSS 20-100+ FILES) ---
        rag_citations = []
        if scope in ("all", "documents", "docs"):
            try:
                rag_res = await project_rag_service.build_rag_context(db, effective_pid, question, max_tokens=1800)
                if rag_res.get("context_markdown"):
                    knowledge_sections.append(rag_res["context_markdown"])
                rag_citations = rag_res.get("citations", [])
            except Exception as re_err:
                logger.warning(f"Error retrieving project document RAG context: {re_err}")

        full_knowledge_context = "\n\n".join(knowledge_sections) if knowledge_sections else "(Không có dữ liệu tri thức nào phù hợp với phạm vi đã chọn)"

        # --- D. MULTI-TURN CHAT HISTORY ---
        history_section = ""
        if chat_history:
            recent = chat_history[-6:]
            h_lines = []
            for msg in recent:
                role = "User" if msg.get("role") == "user" else "Project Brain Copilot"
                c = (msg.get("content") or "").strip()
                if c:
                    h_lines.append(f"{role}: {c}")
            if h_lines:
                history_section = "\nPrevious Conversation History (Multi-turn Context):\n" + "\n".join(h_lines) + "\n"

        prompt = f"""You are the Project Brain AI Copilot for this enterprise software engineering project.
Answer the user's question with high precision and clarity based on the multi-source project knowledge provided below.

{full_knowledge_context}
{history_section}
Current User Question:
"{question}"

Instructions:
1. Provide a comprehensive, executive answer in Vietnamese directly addressing the question using structured Markdown.
2. If this is a follow-up question in the conversation history, maintain continuity and context from previous turns.
3. Explicitly cite concrete sources (Meetings, Work Items, Evidence Quotes) that support your answer.
4. List any "Known Unknowns" (open questions, unfinalized specs, or aspects that still require confirmation with the client).
5. Provide 3 smart "Follow-up Suggestions" (relevant next questions the BrSE might want to ask next).
6. Return strict JSON matching:
{{
  "answer": "Structured markdown answer in Vietnamese...",
  "confidence": 0.95,
  "citations": [
    {{
      "source_type": "meeting | work_item | chat | doc",
      "title": "Tên cuộc họp hoặc Work Item",
      "quote": "Trích dẫn bằng chứng hoặc lý do cụ thể",
      "author": "Người phụ trách hoặc bên phát biểu (nếu có)",
      "date": "YYYY-MM-DD hoặc thời gian (nếu có)"
    }}
  ],
  "known_unknowns": [
    "Vấn đề tồn đọng hoặc điểm chưa chốt cần làm rõ với khách hàng Nhật"
  ],
  "follow_up_suggestions": [
    "Câu hỏi gợi ý 1...",
    "Câu hỏi gợi ý 2...",
    "Câu hỏi gợi ý 3..."
  ]
}}"""

        # Provider fallback chain: preferred -> next providers
        if provider_name == "groq":
            provider_chain = ["groq", "gemini"]
        elif provider_name == "gemini":
            provider_chain = ["gemini", "groq"]
        elif not provider_name or provider_name.lower() in ("auto", "default"):
            provider_chain = ["groq", "gemini"]
        else:
            provider_chain = [provider_name, "groq", "gemini"]

        parsed = {}
        for prov_candidate in provider_chain:
            provider = provider_registry.get_provider(prov_candidate)
            if not provider:
                continue
            try:
                target_model = model if (prov_candidate == provider_name and model and model.strip()) else None
                logger.info(f"Asking Project Brain with provider '{prov_candidate}' (model: {target_model or 'default'})...")
                use_json_mode = True if prov_candidate == "gemini" else False
                resp = await provider.generate(
                    prompt=prompt,
                    system_instruction="You are an evidence-based Project Brain Copilot. Synthesize answers accurately across meetings, work items, and evidence quotes in valid JSON.",
                    model=target_model,
                    temperature=0.1,
                    max_tokens=950,
                    json_mode=use_json_mode
                )

                if resp and resp.text:
                    parsed = clean_json_response(resp.text)
                    if parsed and isinstance(parsed, dict) and parsed.get("answer"):
                        logger.info(f"Project Brain Q&A successfully produced by provider: {prov_candidate}")
                        break
            except Exception as e:
                logger.warning(f"Project Brain Q&A failed with provider {prov_candidate}: {e}")

        if not parsed or not parsed.get("answer"):
            # Intelligent fallback based on local work items & meetings
            matching_items = [i for i in work_items_all if any(w.lower() in i.title.lower() for w in question.split())]
            matching_meetings = [m for m in meetings if any(w.lower() in (m.title or "").lower() for w in question.split())]

            ans_lines = [f"Đã tìm kiếm trong tri thức dự án ({len(meetings)} cuộc họp, {len(work_items_all)} work items)."]
            if matching_items:
                ans_lines.append(f"Tìm thấy {len(matching_items)} mục công việc liên quan trực tiếp:")
                for it in matching_items[:3]:
                    ans_lines.append(f"- [{it.item_type}] **{it.title}** ({it.status}): {it.description[:150]}")
            elif matching_meetings:
                ans_lines.append(f"Tìm thấy các cuộc họp liên quan:")
                for m in matching_meetings[:3]:
                    ans_lines.append(f"- **{m.title}** ({m.meeting_date})")
            else:
                ans_lines.append("Hiện tại chưa ghi nhận quyết định chính thức đã chốt cho câu hỏi này trong biên bản dự án.")

            citations_fb = []
            for it in matching_items[:2]:
                citations_fb.append({
                    "source_type": "work_item",
                    "title": it.title,
                    "quote": it.description[:100],
                    "author": it.assignee or "Team",
                    "date": "N/A"
                })
            for m in matching_meetings[:2]:
                citations_fb.append({
                    "source_type": "meeting",
                    "title": m.title,
                    "quote": "Biên bản cuộc họp liên quan",
                    "author": "Team",
                    "date": m.meeting_date
                })

            return {
                "answer": "\n\n".join(ans_lines),
                "confidence": 0.70,
                "citations": citations_fb,
                "known_unknowns": ["Cần xác nhận lại với khách hàng hoặc PM trong cuộc họp tiếp theo."],
                "follow_up_suggestions": [
                    "Các cuộc họp gần nhất đã thống nhất những nội dung gì?",
                    "Hiện tại có những công việc nào đang chờ khách hàng xác nhận?",
                    "Tiến trình tổng quan của dự án qua các mốc thời gian?"
                ]
            }

        final_citations = parsed.get("citations", [])
        if rag_citations:
            for rc in rag_citations:
                final_citations.append({
                    "source_type": "doc",
                    "title": rc["source"],
                    "quote": f"Trích dẫn từ {rc['citation']}",
                    "author": "Project Documents",
                    "date": "Tài liệu dự án"
                })

        return {
            "answer": parsed.get("answer", ""),
            "confidence": parsed.get("confidence", 0.95),
            "citations": final_citations,
            "known_unknowns": parsed.get("known_unknowns", []),
            "follow_up_suggestions": parsed.get("follow_up_suggestions", [
                "Chi tiết các quyết định liên quan trong cuộc họp gần nhất?",
                "Ai là người phụ trách chính các hạng mục này?",
                "Còn những vấn đề tồn đọng nào cần khách hàng xác nhận?"
            ])
        }
