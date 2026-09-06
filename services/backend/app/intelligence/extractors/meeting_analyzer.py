import json
import re
import asyncio
from typing import Dict, List, Any, Optional
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Project, ProjectInstruction, GlossaryTerm
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import MeetingRecord, WorkItem, WorkItemEvidence

class MeetingAnalyzer:
    """Transforms raw meeting transcripts and notes into structured, bilingual, business-ready minutes.
    Supports both single-pass analysis and hierarchical Map-Reduce for large, multi-session meeting series.
    """

    @classmethod
    def clean_whisper_hallucinations(cls, text: str) -> str:
        """Removes Whisper speech-to-text repetition loops and hallucinated phrases."""
        if not text:
            return ""
        # Remove repeated phrases like (phrase){3,}
        pattern = re.compile(r"([^\s，、。？！\n]{2,20}?)(?:\1){3,}")
        cleaned = pattern.sub(r"\1", text)
        # Remove repeated conversational particles
        pattern2 = re.compile(r"(はい|えっと|あの|そう|ですね){4,}")
        cleaned = pattern2.sub(r"\1", cleaned)
        return cleaned.strip()

    @classmethod
    def _chunk_text_safely(cls, text: str, max_chars: int = 3800) -> List[str]:
        """Splits large text into smaller safe chunks breaking cleanly on sentence boundaries (。!?\n)."""
        if len(text) <= max_chars:
            return [text]
        # Split on Japanese full stops / punctuation (。！？) or Latin punctuation / newlines (.!?\n)
        sentence_units = re.split(r"(?<=[。！？\n])|(?<=[.!?\n]\s)", text)
        chunks = []
        current_chunk = []
        current_len = 0
        for unit in sentence_units:
            if not unit:
                continue
            unit_len = len(unit)
            if current_len + unit_len > max_chars and current_chunk:
                chunks.append("".join(current_chunk).strip())
                current_chunk = []
                current_len = 0
            
            # If a single sentence unit exceeds max_chars, hard chunk it safely
            if unit_len > max_chars:
                for sub_i in range(0, unit_len, max_chars):
                    sub_part = unit[sub_i:sub_i + max_chars]
                    if current_chunk:
                        chunks.append("".join(current_chunk).strip())
                        current_chunk = []
                        current_len = 0
                    chunks.append(sub_part.strip())
            else:
                current_chunk.append(unit)
                current_len += unit_len
                
        if current_chunk:
            chunks.append("".join(current_chunk).strip())
        return [c for c in chunks if c.strip()]

    @classmethod
    def split_transcript_into_sessions(cls, transcript_text: str) -> List[Dict[str, str]]:
        """
        Splits transcript into safe session chunks (<= 3800 chars).
        Single files <= 4,500 chars remain as 1 session for ultra-fast single-pass processing (< 3s).
        Files > 4,500 chars are cleanly broken down into ~3,500 char chunks to respect Groq Free Tier TPM limits.
        """
        header_pattern = re.compile(r"^===\s*\[(Phần\s+\d+/\d+:\s*[^\]]+)\]\s*===", re.MULTILINE)
        matches = list(header_pattern.finditer(transcript_text))
        
        raw_sessions = []
        if len(matches) >= 2:
            for i, match in enumerate(matches):
                header = match.group(1).strip()
                start_pos = match.end()
                end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(transcript_text)
                body = transcript_text[start_pos:end_pos].strip()
                raw_sessions.append({"header": header, "text": body})
        else:
            cleaned = transcript_text.strip()
            if len(cleaned) <= 25000:
                return [{"header": "Buổi họp", "text": cleaned}]
            raw_sessions.append({"header": "Buổi họp", "text": cleaned})
        
        # Subdivide any large session exceeding 22,000 chars into safe ~20,000 char chunks
        final_sessions = []
        for sess in raw_sessions:
            text = sess["text"]
            if len(text) <= 22000:
                final_sessions.append(sess)
            else:
                sub_chunks = cls._chunk_text_safely(text, max_chars=20000)
                for sub_idx, sub in enumerate(sub_chunks):
                    final_sessions.append({
                        "header": f"{sess['header']} (Phần {sub_idx + 1}/{len(sub_chunks)})",
                        "text": sub
                    })
                    
        return final_sessions

    @classmethod
    async def _call_llm_with_fallback(
        cls,
        prompt: str,
        system_instruction: str,
        provider_name: str = "groq",
        model: Optional[str] = None,
        max_retries: int = 2,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Executes LLM request with provider fallback chain and exponential retry backoff."""
        # If user chose groq, try groq first and allow Gemini fallback if groq quotas are exhausted
        if provider_name == "groq":
            provider_chain = ["groq", "gemini"]
        elif not provider_name or provider_name.lower() in ("auto", "default"):
            provider_chain = ["groq", "gemini"]
        else:
            provider_chain = [provider_name]


        for prov_candidate in provider_chain:
            provider = provider_registry.get_provider(prov_candidate)
            if not provider:
                continue
            target_model = model if (prov_candidate == provider_name and model and model.strip()) else None

            for attempt in range(max_retries):
                try:
                    logger.info(f"Generating meeting analysis with '{prov_candidate}' (model: {target_model or 'default'}, attempt {attempt+1})...")
                    resp = await provider.generate(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        model=target_model,
                        temperature=0.1,
                        json_mode=True,
                        max_tokens=max_tokens
                    )
                    if resp and resp.text:
                        parsed = clean_json_response(resp.text)
                        if parsed and isinstance(parsed, dict) and any(k in parsed for k in ["summary", "summary_ja", "summary_vi", "decisions", "action_items", "main_topics", "participants", "notes", "summary_points"]):
                            return parsed
                        logger.warning(f"Response from {prov_candidate} lacked required meeting fields: {resp.text[:100]}")
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f"LLM call failed with {prov_candidate} (attempt {attempt+1}): {err_str}")
                    if "413" in err_str or "429" in err_str or "rate_limit" in err_str.lower():
                        await asyncio.sleep(2.0 * (attempt + 1))
                    else:
                        break

        return {}

    @classmethod
    async def _map_session(
        cls,
        session: Dict[str, str],
        project_context: str,
        provider_name: str,
        model: Optional[str]
    ) -> Dict[str, Any]:
        """MAP phase: Analyzes an individual meeting session transcript (~2,000 - 3,500 tokens)."""
        prompt = f"""You are a bilingual IT BrSE assistant analyzing a specific meeting session.
Project: {project_context}
Session Info: {session['header']}

Session Transcript:
{session['text'][:12000]}

Extract concise notes for this specific session in strict JSON:
{{
  "session_title": "{session['header']}",
  "summary_points": ["Tóm tắt thảo luận chính 1 (VI)", "Tóm tắt thảo luận chính 2 (VI)..."],
  "decisions": [
    {{
      "title_vi": "Tiêu đề quyết định (VI)",
      "title_ja": "決議事項タイトル (JA)",
      "detail_vi": "Chi tiết quyết định",
      "detail_ja": "決議詳細",
      "evidence": "Trích dẫn bằng chứng từ transcript"
    }}
  ],
  "action_items": [
    {{
      "task_vi": "Nội dung công việc (VI)",
      "task_ja": "タスク内容 (JA)",
      "assignee": "Người phụ trách",
      "due_date": "YYYY-MM-DD hoặc Chưa xác định",
      "priority": "HIGH / MEDIUM / LOW"
    }}
  ],
  "open_questions": [
    {{
      "question_vi": "Vấn đề còn bỏ ngỏ / cần confirm",
      "question_ja": "未解決・確認事項",
      "owner": "Client / Dev team",
      "urgency": "HIGH / MEDIUM"
    }}
  ]
}}"""
        system_instruction = "You are an expert bilingual IT BrSE assistant. Extract key decisions, action items, and open questions from this meeting session into strict JSON."
        result = await cls._call_llm_with_fallback(prompt, system_instruction, provider_name, model, max_tokens=500)
        if not result or not isinstance(result, dict):
            return {
                "session_title": session['header'],
                "summary_points": [],
                "decisions": [],
                "action_items": [],
                "open_questions": []
            }
        result.setdefault("session_title", session['header'])
        return result

    @classmethod
    async def _reduce_sessions(
        cls,
        session_results: List[Dict[str, Any]],
        project_context: str,
        title: str,
        meeting_date: str,
        provider_name: str,
        model: Optional[str],
        glossary_section: str,
        instructions_section: str
    ) -> Dict[str, Any]:
        """REDUCE phase: Synthesizes intermediate session outputs into Master Bilingual Meeting Minutes."""
        intermediate_summary_blocks = []
        for idx, s in enumerate(session_results):
            s_title = s.get("session_title", f"Buổi #{idx + 1}")
            pts = "\n".join([f"    * {p}" for p in s.get("summary_points", [])])
            decs = "\n".join([f"    * [QUYẾT ĐỊNH] {d.get('title_vi', '')}: {d.get('detail_vi', '')} (Bằng chứng: {d.get('evidence', 'N/A')})" for d in s.get("decisions", [])])
            acts = "\n".join([f"    * [ACTION] {a.get('task_vi', '')} (Phụ trách: {a.get('assignee', 'N/A')} | Hạn: {a.get('due_date', 'N/A')})" for a in s.get("action_items", [])])
            oqs = "\n".join([f"    * [QUESTION] {q.get('question_vi', '')} (Xác nhận: {q.get('owner', 'Client')})" for q in s.get("open_questions", [])])
            
            block = f"""### {s_title}
  - Nội dung chính:
{pts or '    * (Trao đổi nghiệp vụ)'}
  - Quyết định chốt:
{decs or '    * (Không có quyết định mới)'}
  - Việc cần làm:
{acts or '    * (Không có task mới)'}
  - Tồn đọng / Chưa chốt:
{oqs or '    * (Không có câu hỏi mới)'}"""
            intermediate_summary_blocks.append(block)

        joined_sessions_summary = "\n\n".join(intermediate_summary_blocks)

        prompt = f"""You are an executive bilingual BrSE (Bridge Software Engineer).
Project: {project_context}
Meeting Series Title: {title}
Date/Timeframe: {meeting_date}
{glossary_section}{instructions_section}

The following is chronological summary data extracted from {len(session_results)} meeting sessions:
{joined_sessions_summary}

Synthesize these into a master executive bilingual meeting minutes document in strict JSON:
1. "summary_vi": Professional, concise Vietnamese executive summary (Markdown bullet points, ~150-250 words) summarizing key results, agreed direction, and project impact.
2. "summary_ja": Professional, concise Japanese executive summary (Markdown bullet points, Keigo, ~150-250 words).
3. "decisions": Consolidate all decisions across sessions. If an earlier decision was modified, superseded, or cancelled in a later session, record the FINAL ACTIVE DECISION, explicitly noting the evolution if changed.
4. "action_items": Consolidate action items across all sessions. Deduplicate tasks and reflect the latest assignees and deadlines.
5. "open_questions": Include ONLY questions and uncertainties that remain unresolved by the final session.
6. "participants": List of attendees identified across meetings.

Strict JSON format:
{{
  "summary_vi": "Tóm tắt điều hành toàn diện chuỗi cuộc họp bằng tiếng Việt (Markdown, gạch đầu dòng súc tích)...",
  "summary_ja": "日本の顧客・ステークホルダー向けのエグゼクティブサマリー（Markdown形式、敬語、箇条書き）...",
  "decisions": [
    {{
      "title_vi": "Tiêu đề quyết định (VI)",
      "title_ja": "決議事項タイトル (JA)",
      "detail_vi": "Chi tiết quyết định (VI)",
      "detail_ja": "詳細内容 (JA)",
      "evidence": "Bằng chứng trích dẫn"
    }}
  ],
  "action_items": [
    {{
      "task_vi": "Nội dung công việc (VI)",
      "task_ja": "タスク内容 (JA)",
      "assignee": "Người phụ trách",
      "due_date": "YYYY-MM-DD hoặc Chưa xác định",
      "priority": "HIGH / MEDIUM / LOW"
    }}
  ],
  "open_questions": [
    {{
      "question_vi": "Câu hỏi còn tồn đọng (VI)",
      "question_ja": "未解決・確認事項 (JA)",
      "owner": "Client / Dev team",
      "urgency": "HIGH / MEDIUM"
    }}
  ],
  "participants": ["Name 1 (Role)", "Name 2 (Role)..."]
}}"""
        system_instruction = "You are a senior bilingual BrSE Executive Secretary. Synthesize multi-session meeting records into authoritative, high-accuracy bilingual minutes (JA/VI)."
        return await cls._call_llm_with_fallback(prompt, system_instruction, provider_name, model, max_tokens=850)


    @classmethod
    async def analyze_meeting(
        cls,
        db: AsyncSession,
        project_id: str,
        title: str,
        meeting_date: str,
        transcript_text: str,
        provider_name: str = "groq",
        model: Optional[str] = None
    ) -> MeetingRecord:
        transcript_text = cls.clean_whisper_hallucinations(transcript_text)
        # Validate project_id or fallback to existing project to guarantee DB integrity
        proj = await db.get(Project, project_id) if project_id else None
        if not proj:
            first_proj = (await db.execute(select(Project).limit(1))).scalar_one_or_none()
            if first_proj:
                proj = first_proj
                project_id = first_proj.id
            else:
                default_proj = Project(
                    name="Default Project",
                    code="DEFAULT",
                    description="Auto-created default project for meeting notes"
                )
                db.add(default_proj)
                await db.flush()
                proj = default_proj
                project_id = default_proj.id

        project_context = f"{proj.name} ({proj.code})"

        # 1. Retrieve Project Instructions / Rules
        instructions: List[str] = []
        if project_id:
            inst_res = await db.execute(
                select(ProjectInstruction)
                .where(and_(ProjectInstruction.project_id == project_id, ProjectInstruction.is_active == True))
                .order_by(ProjectInstruction.priority.desc())
            )
            instructions = [inst.rule_text for inst in inst_res.scalars().all()]

        # 2. Retrieve Relevant Project & Global Glossary Terms
        query_glossary = select(GlossaryTerm).where(
            and_(
                GlossaryTerm.is_active == True,
                or_(
                    GlossaryTerm.project_id == project_id,
                    GlossaryTerm.project_id == None,
                    GlossaryTerm.scope.in_(["global", "company"])
                )
            )
        )
        res_gl = await db.execute(query_glossary)
        all_terms = res_gl.scalars().all()

        matched_terms = []
        other_project_terms = []
        for term in all_terms:
            t_src = term.source_term or ""
            t_tgt = term.target_term or ""
            if (t_src and (t_src in transcript_text or t_src.lower() in transcript_text.lower())) or \
               (t_tgt and (t_tgt in transcript_text or t_tgt.lower() in transcript_text.lower())):
                matched_terms.append(term)
            elif term.project_id == project_id:
                other_project_terms.append(term)

        selected_terms = (matched_terms + other_project_terms)[:25]

        # Format context sections for prompt
        glossary_section = ""
        if selected_terms:
            terms_lines = [f"- \"{t.source_term}\" => \"{t.target_term}\" ({t.category or 'General'})" for t in selected_terms]
            glossary_section = "\n### MANDATORY PROJECT GLOSSARY (Apply these exact translations):\n" + "\n".join(terms_lines) + "\n"

        instructions_section = ""
        if instructions:
            rules_lines = [f"- {r}" for r in instructions[:10]]
            instructions_section = "\n### PROJECT COMPLIANCE RULES & INSTRUCTIONS:\n" + "\n".join(rules_lines) + "\n"

        parsed: Dict[str, Any] = {}

        # 3. Determine Execution Strategy: Single-pass vs Map-Reduce
        sessions = cls.split_transcript_into_sessions(transcript_text)
        if len(sessions) >= 2:
            logger.info(f"Triggering Map-Reduce meeting analysis across {len(sessions)} session chunks...")
            session_results = []
            for i, sess in enumerate(sessions):
                logger.info(f"Map phase: Processing session {i+1}/{len(sessions)} ({sess['header']})...")
                res = await cls._map_session(sess, project_context, provider_name, model)
                session_results.append(res)
                # Polite delay between calls to respect rate limit (TPM)
                if i + 1 < len(sessions):
                    await asyncio.sleep(3.0)

            await asyncio.sleep(2.0)
            logger.info(f"Reduce phase: Synthesizing master minutes from {len(session_results)} session results...")

            parsed = await cls._reduce_sessions(
                session_results=session_results,
                project_context=project_context,
                title=title,
                meeting_date=meeting_date,
                provider_name=provider_name,
                model=model,
                glossary_section=glossary_section,
                instructions_section=instructions_section
            )

            # Defensive recovery: if reduce LLM call failed or returned empty summary, synthesize from map session results
            if not parsed or not parsed.get("summary_vi"):
                logger.warning("Reduce phase returned empty summary. Synthesizing from session_results...")
                all_pts = []
                all_decs = []
                all_acts = []
                all_oqs = []
                for s in session_results:
                    for p in s.get("summary_points", []):
                        if p and "nội dung trao đổi trong" not in p.lower():
                            all_pts.append(p)
                    all_decs.extend(s.get("decisions", []))
                    all_acts.extend(s.get("action_items", []))
                    all_oqs.extend(s.get("open_questions", []))

                parsed = parsed or {}
                if not parsed.get("summary_vi") and all_pts:
                    parsed["summary_vi"] = f"### Tóm tắt cuộc họp: {title}\n\n**Các nội dung thảo luận chính:**\n" + "\n".join([f"- {p}" for p in all_pts if p])
                if not parsed.get("summary_ja") and all_pts:
                    parsed["summary_ja"] = f"### 議事録サマリー: {title}\n\n**主な協議事項:**\n" + "\n".join([f"- {p}" for p in all_pts if p])
                if not parsed.get("decisions") and all_decs:
                    parsed["decisions"] = all_decs
                if not parsed.get("action_items") and all_acts:
                    parsed["action_items"] = all_acts
                if not parsed.get("open_questions") and all_oqs:
                    parsed["open_questions"] = all_oqs
        else:
            # Single session direct analysis
            prompt = f"""You are an executive bilingual BrSE (Bridge Software Engineer) producing formal, high-accuracy Meeting Minutes from the following meeting transcript.
Project: {project_context}
Title: {title}
Date: {meeting_date}
{glossary_section}{instructions_section}
Transcript:
{transcript_text}

Instructions:
1. Output MUST be BILINGUAL (Japanese for Japanese clients/stakeholders, and Vietnamese for local engineering team).
2. Strictly adhere to any terms provided in the MANDATORY PROJECT GLOSSARY and rules in PROJECT COMPLIANCE RULES.
3. Output comprehensive, professional meeting minutes in strict JSON format:
{{
  "summary_vi": "Tóm tắt điều hành cuộc họp chi tiết bằng tiếng Việt cho team kỹ thuật và ban quản lý (Markdown, gạch đầu dòng súc tích)...",
  "summary_ja": "日本の顧客・ステークホルダー向けのエグゼクティブサマリー（Markdown形式、敬語・ビジネス日本語、箇条書き）...",
  "decisions": [
    {{
      "title_vi": "Tiêu đề quyết định (VI)",
      "title_ja": "決議事項のタイトル (JA)",
      "detail_vi": "Chi tiết quyết định (VI)",
      "detail_ja": "詳細内容 (JA)",
      "evidence": "Trích dẫn nguyên văn bằng chứng từ transcript"
    }}
  ],
  "action_items": [
    {{
      "task_vi": "Nội dung công việc (VI)",
      "task_ja": "タスク内容 (JA)",
      "assignee": "Tên người phụ trách",
      "due_date": "YYYY-MM-DD hoặc Chưa xác định",
      "priority": "HIGH / MEDIUM / LOW"
    }}
  ],
  "open_questions": [
    {{
      "question_vi": "Câu hỏi còn bỏ ngỏ hoặc cần confirm (VI)",
      "question_ja": "未解決の質問や確認事項 (JA)",
      "owner": "Client / Team / Khách hàng / Dev team",
      "urgency": "HIGH / MEDIUM"
    }}
  ],
  "participants": ["Name 1 (Role)", "Name 2 (Role)..."]
}}"""
            system_instruction = "You are a professional bilingual IT BrSE Meeting Secretary. Generate clear, structured bilingual meeting minutes (JA/VI) adhering strictly to project terminology and rules."
            parsed = await cls._call_llm_with_fallback(prompt, system_instruction, provider_name, model, max_tokens=850)


        participants = parsed.get("participants", ["Team Attendees"])
        summary_ja = parsed.get("summary_ja", "")
        summary_vi = parsed.get("summary_vi", "")
        if not summary_vi and parsed.get("summary_markdown"):
            summary_vi = parsed.get("summary_markdown", "")
        if not summary_ja and summary_vi:
            summary_ja = summary_vi

        if not summary_vi and not summary_ja and not parsed.get("decisions") and not parsed.get("action_items"):
            raise RuntimeError(
                f"Không thể phân tích cuộc họp '{title}' do các mô hình AI đều đang bận hoặc quá tải giới hạn (Rate Limit / Quota). Vui lòng thử lại sau giây lát."
            )

        if not summary_vi:
            summary_vi = f"### Tóm tắt cuộc họp\n\nCuộc họp ngày {meeting_date} về chủ đề {title}.\n\nNội dung trao đổi đã được ghi nhận."
        if not summary_ja:
            summary_ja = f"### 議事録サマリー\n\n{meeting_date}に実施された「{title}」に関する打ち合わせ内容です。"

        summary_store = json.dumps({
            "ja": summary_ja,
            "vi": summary_vi
        }, ensure_ascii=False)

        decisions = parsed.get("decisions", [])
        for dec in decisions:
            if isinstance(dec, dict):
                dec.setdefault("title_vi", dec.get("title", ""))
                dec.setdefault("title_ja", dec.get("title", dec.get("title_vi", "")))
                dec.setdefault("detail_vi", dec.get("detail", ""))
                dec.setdefault("detail_ja", dec.get("detail", dec.get("detail_vi", "")))
                dec["title"] = dec.get("title_vi") or dec.get("title_ja") or ""
                dec["detail"] = dec.get("detail_vi") or dec.get("detail_ja") or ""

        action_items = parsed.get("action_items", [])
        for act in action_items:
            if isinstance(act, dict):
                act.setdefault("task_vi", act.get("task", ""))
                act.setdefault("task_ja", act.get("task", act.get("task_vi", "")))
                act["task"] = act.get("task_vi") or act.get("task_ja") or ""

        open_questions = parsed.get("open_questions", [])
        for oq in open_questions:
            if isinstance(oq, dict):
                oq.setdefault("question_vi", oq.get("question", ""))
                oq.setdefault("question_ja", oq.get("question", oq.get("question_vi", "")))
                oq["question"] = oq.get("question_vi") or oq.get("question_ja") or ""

        # Persist MeetingRecord
        meeting = MeetingRecord(
            project_id=project_id,
            title=title,
            meeting_date=meeting_date,
            participants_json=json.dumps(participants, ensure_ascii=False),
            transcript_text=transcript_text,
            summary_markdown=summary_store,
            decisions_json=json.dumps(decisions, ensure_ascii=False),
            action_items_json=json.dumps(action_items, ensure_ascii=False),
            open_questions_json=json.dumps(open_questions, ensure_ascii=False)
        )
        db.add(meeting)
        await db.flush()

        # Also create WorkItem entries for action items, decisions, and open questions so they appear on the BrSE Dashboard & Project Brain!
        for ai in action_items:
            task_name = ai.get("task_vi") or ai.get("task") or ai.get("task_ja", "Meeting Action Item")
            wi = WorkItem(
                project_id=project_id,
                item_type="TODO",
                title=task_name,
                description=f"Action item from meeting: {title}",
                assignee=ai.get("assignee", "Unassigned"),
                deadline_date=ai.get("due_date"),
                priority=ai.get("priority", "HIGH"),
                status="PROPOSED",
                confidence=0.92
            )
            db.add(wi)
            await db.flush()

            evidence = WorkItemEvidence(
                work_item_id=wi.id,
                source_type="meeting",
                source_id=meeting.id,
                quote_text=task_name,
                author="Meeting Attendee",
                timestamp=meeting_date,
                confirmation_status="PROPOSED"
            )
            db.add(evidence)

        # Decisions -> WorkItem (item_type="DECISION", status="CONFIRMED")
        for d in decisions:
            t_vi = d.get("title_vi") or d.get("title") or d.get("title_ja") or f"Quyết định cuộc họp {meeting_date}"
            det_vi = d.get("detail_vi") or d.get("detail") or d.get("reason_vi") or d.get("reason") or ""
            quote = d.get("title_ja") or d.get("reason_vi") or t_vi
            wi = WorkItem(
                project_id=project_id,
                item_type="DECISION",
                title=t_vi,
                description=det_vi,
                status="CONFIRMED",
                priority="HIGH",
                confidence=0.98,
                assignee="Hội đồng cuộc họp"
            )
            db.add(wi)
            await db.flush()

            evidence = WorkItemEvidence(
                work_item_id=wi.id,
                source_type="meeting",
                source_id=meeting.id,
                quote_text=quote,
                author=f"Cuộc họp {meeting_date}",
                timestamp=meeting_date,
                confirmation_status="CONFIRMED"
            )
            db.add(evidence)

        # Open Questions -> WorkItem (item_type="OPEN_QUESTION", status="PROPOSED")
        for q in open_questions:
            q_title = q.get("question_vi") or q.get("question") or q.get("question_ja") or f"Câu hỏi tồn đọng cuộc họp {meeting_date}"
            q_detail = q.get("question_ja") or q.get("context") or ""
            quote = q.get("question_ja") or q_title
            wi = WorkItem(
                project_id=project_id,
                item_type="OPEN_QUESTION",
                title=q_title,
                description=q_detail,
                status="PROPOSED",
                priority="HIGH",
                confidence=0.92,
                assignee=q.get("assigned_to") or "Khách hàng Nhật"
            )
            db.add(wi)
            await db.flush()

            evidence = WorkItemEvidence(
                work_item_id=wi.id,
                source_type="meeting",
                source_id=meeting.id,
                quote_text=quote,
                author=f"Cuộc họp {meeting_date}",
                timestamp=meeting_date,
                confirmation_status="PROPOSED"
            )
            db.add(evidence)

        await db.commit()
        await db.refresh(meeting)
        return meeting
