import json
from typing import Dict, List, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import re
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import MeetingRecord

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
    return "Trao đổi kỹ thuật và nghiệp vụ dự án."

def compute_relevance_scores(meetings: List[Any], question: str, chat_history: Optional[List[Dict[str, str]]] = None) -> List[tuple]:
    """2-Tier RAG Scorer: ranks meetings by semantic relevance to user question."""
    q_lower = question.lower()
    
    # Extract query keywords (words >= 2 chars)
    query_words = set(re.findall(r"[\w\u00C0-\u024F\u1EA0-\u1EF9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]{2,}", q_lower))
    
    # Temporal & milestone intent detectors
    has_jun = any(k in q_lower for k in ["tháng 6", "t6", "06", "jun", "june", "18/6", "25/6"])
    has_jul = any(k in q_lower for k in ["tháng 7", "t7", "07", "jul", "july", "02/7", "10/7", "16/7", "30/7"])
    has_aug = any(k in q_lower for k in ["tháng 8", "t8", "08", "aug", "august", "06/8", "20/8"])
    is_overview = any(k in q_lower for k in ["tiến trình", "tóm tắt", "tổng quan", "các mốc", "toàn bộ", "qua các", "quá trình", "timeline", "overview", "tất cả"])
    
    scored = []
    for idx, m in enumerate(meetings):
        score = 1.0 # baseline score
        
        # Parse fields
        summary_vi = m.summary_markdown or ""
        try:
            s_obj = json.loads(m.summary_markdown)
            if isinstance(s_obj, dict):
                summary_vi = s_obj.get("vi", "") or m.summary_markdown or ""
        except Exception:
            pass
            
        try:
            decs = json.loads(m.decisions_json or "[]")
        except Exception:
            decs = []
            
        try:
            acts = json.loads(m.action_items_json or "[]")
        except Exception:
            acts = []
            
        try:
            oqs = json.loads(m.open_questions_json or "[]")
        except Exception:
            oqs = []
            
        # 1. Temporal matching
        m_date = m.meeting_date or ""
        if has_jun and "-06-" in m_date:
            score += 8.0
        if has_jul and "-07-" in m_date:
            score += 8.0
        if has_aug and "-08-" in m_date:
            score += 8.0
            
        # 2. Overview / timeline query: spread boost across milestone anchors
        if is_overview:
            if idx == 0 or idx == len(meetings) - 1:
                score += 5.0 # landmark meetings
            elif idx == len(meetings) // 2:
                score += 4.0
            else:
                score += 2.0
                
        # 3. Content matching against title, summary, decisions, action items
        m_title_lower = (m.title or "").lower()
        m_summary_lower = summary_vi.lower()
        
        for w in query_words:
            if len(w) <= 2 and w not in ["ui", "db", "api", "kot"]:
                continue
            if w in m_title_lower:
                score += 5.0
            if w in m_summary_lower:
                score += 2.5
            for d in decs:
                d_text = f"{d.get('title_vi', '')} {d.get('title', '')} {d.get('detail_vi', '')}".lower()
                if w in d_text:
                    score += 4.0
            for a in acts:
                a_text = f"{a.get('task_vi', '')} {a.get('task', '')} {a.get('assignee', '')}".lower()
                if w in a_text:
                    score += 3.0

        scored.append((m, score, {
            "summary_vi": summary_vi,
            "decisions": decs,
            "action_items": acts,
            "open_questions": oqs
        }))
        
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored

class AskMeetingsEngine:
    """Evidence-based Cross-Meeting Q&A Engine using 2-Tier RAG across historical meetings, decisions, and action items."""

    @classmethod
    async def ask_meetings(
        cls,
        db: AsyncSession,
        project_id: Optional[str],
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        provider_name: str = "groq",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Answers questions by synthesizing information across project meetings using 2-Tier RAG."""
        # 1. Fetch relevant meetings
        stmt = select(MeetingRecord)
        if project_id and project_id not in ("all", "default-project", ""):
            stmt = stmt.where(MeetingRecord.project_id == project_id)
        stmt = stmt.order_by(MeetingRecord.meeting_date.asc())
        
        res = await db.execute(stmt)
        meetings = res.scalars().all()

        if not meetings:
            return {
                "answer": "Chưa có dữ liệu cuộc họp nào được lưu trữ trong dự án để phân tích và trả lời câu hỏi.",
                "citations": [],
                "evolution_notes": []
            }

        # 2. Build 2-Tier RAG Context
        scored = compute_relevance_scores(meetings, question, chat_history)

        # Tier 1: Global Chronological Timeline Index across ALL meetings in project
        timeline_lines = ["### TẦNG 1: DÒNG THỜI GIAN TOÀN DỰ ÁN (GLOBAL TIMELINE INDEX):"]
        for m, score, data in sorted(scored, key=lambda x: x[0].meeting_date):
            gist = extract_one_line_gist(data["summary_vi"], data["decisions"])
            decs_cnt = len(data["decisions"])
            acts_cnt = len(data["action_items"])
            timeline_lines.append(
                f"• [{m.meeting_date}] \"{m.title}\" (ID: {m.id}): {gist} | [{decs_cnt} quyết định, {acts_cnt} việc]"
            )
        tier1_timeline = "\n".join(timeline_lines)

        # Tier 2: Deep Semantic Focus (Top 4 most relevant meetings, sorted chronologically)
        top_k = min(4, len(meetings))
        top_meetings = scored[:top_k]
        top_meetings.sort(key=lambda x: x[0].meeting_date)

        deep_blocks = [f"### TẦNG 2: DỮ LIỆU CHI TIẾT CÁC CUỘC HỌP TRỌNG TÂM LIÊN QUAN NHẤT ({top_k}/{len(meetings)} CUỘC HỌP):"]
        for m, score, data in top_meetings:
            s_vi = data['summary_vi']
            if len(s_vi) > 600:
                s_vi = s_vi[:600] + "..."
            b_lines = [
                f"=== [Cuộc họp: \"{m.title}\" | Ngày: {m.meeting_date} | ID: {m.id}] ===",
                f"Tóm tắt chi tiết (VI):\n{s_vi}"
            ]
            if data["decisions"]:
                b_lines.append("Quyết định đã chốt (Decisions):")
                for d in data["decisions"]:
                    t_str = d.get("title_vi") or d.get("title") or d.get("title_ja", "")
                    dt_str = d.get("detail_vi") or d.get("detail") or d.get("detail_ja", "")
                    ev = f" [Bằng chứng: \"{d.get('evidence')}\"]" if d.get("evidence") else ""
                    b_lines.append(f"  * [QUYẾT ĐỊNH] {t_str}: {dt_str}{ev}")

            if data["action_items"]:
                b_lines.append("Việc cần làm (Action Items):")
                for a in data["action_items"]:
                    t_str = a.get("task_vi") or a.get("task") or a.get("task_ja", "")
                    b_lines.append(f"  * [ACTION] {t_str} (Phụ trách: {a.get('assignee', 'N/A')}, Hạn: {a.get('due_date', 'N/A')})")

            if data["open_questions"]:
                b_lines.append("Vấn đề tồn đọng (Open Questions):")
                for o in data["open_questions"]:
                    q_str = o.get("question_vi") or o.get("question") or o.get("question_ja", "")
                    b_lines.append(f"  * [CHƯA CHỐT] {q_str} (Bên xác nhận: {o.get('owner', 'N/A')})")

            deep_blocks.append("\n".join(b_lines))

        tier2_deep = "\n\n".join(deep_blocks)

        history_section = ""
        if chat_history:
            recent_turns = chat_history[-4:]
            lines = []
            for msg in recent_turns:
                role = "User" if msg.get("role") == "user" else "Meeting Brain Assistant"
                content = (msg.get("content") or "").strip()
                if content:
                    lines.append(f"{role}: {content}")
            if lines:
                history_section = "\n\nPrevious Conversation History (Multi-turn Context):\n" + "\n".join(lines) + "\n"

        prompt = f"""You are the Executive Meeting Brain AI for this software engineering project.
Analyze the 2-tier chronological meeting records below to answer the user's question accurately.

{tier1_timeline}

{tier2_deep}
{history_section}
Current User Question:
"{question}"

Instructions:
1. Provide a comprehensive, accurate answer in Vietnamese directly addressing the question.
2. If this is a follow-up question in the conversation history, maintain continuity and context from previous turns.
3. Synthesize decisions across time: if an earlier decision evolved or changed in a later meeting, explain the evolution clearly and state the final agreed conclusion.
4. Explicitly cite which meeting(s) (Title and Meeting Date) the information is based on.
5. If the question cannot be answered from the meeting notes, be honest and state what is known and what is missing.
6. Return strict JSON matching:
{{
  "answer": "Structured markdown answer in Vietnamese...",
  "citations": [
    {{
      "meeting_id": "id",
      "title": "Tên cuộc họp",
      "meeting_date": "YYYY-MM-DD",
      "quote_or_reason": "Lý do trích dẫn hoặc thông tin liên quan từ cuộc họp này"
    }}
  ],
  "evolution_notes": [
    "Mô tả sự thay đổi/tiến trình quyết định qua các tuần (nếu có)"
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
                logger.info(f"Asking Meeting Brain with provider '{prov_candidate}' (model: {target_model or 'default'})...")
                use_json_mode = True if prov_candidate == "gemini" else False
                resp = await provider.generate(
                    prompt=prompt,
                    system_instruction="You are an executive Meeting Intelligence Assistant. Provide accurate, evidence-based answers in valid JSON format synthesized across multiple meeting records.",
                    model=target_model,
                    temperature=0.1,
                    max_tokens=950,
                    json_mode=use_json_mode
                )

                if resp and resp.text:
                    parsed = clean_json_response(resp.text)
                    if parsed and isinstance(parsed, dict) and parsed.get("answer"):
                        logger.info(f"Meeting Brain Q&A successfully produced by provider: {prov_candidate}")
                        break
            except Exception as e:
                logger.warning(f"Meeting Brain Q&A failed with provider {prov_candidate}: {e}")

        if not parsed or not parsed.get("answer"):
            # Fallback if LLM parsing failed
            rel_meetings = [item[0] for item in scored[:3]] if scored else meetings[:3]
            return {
                "answer": f"Đã tìm thấy {len(meetings)} biên bản cuộc họp nhưng không thể xử lý câu trả lời bằng mô hình AI lúc này. Vui lòng thử lại với AI Provider khác.",
                "citations": [
                    {"meeting_id": m.id, "title": m.title, "meeting_date": m.meeting_date, "quote_or_reason": "Cuộc họp liên quan"}
                    for m in rel_meetings
                ],
                "evolution_notes": []
            }

        return {
            "answer": parsed.get("answer", ""),
            "citations": parsed.get("citations", []),
            "evolution_notes": parsed.get("evolution_notes", [])
        }
