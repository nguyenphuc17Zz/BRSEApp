import os
import json
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Project, GlossaryTerm
from app.intelligence.models import WorkItem, MeetingRecord, ReportRecord
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.reports.slide_report_service import SlideReportService

class ReportService:
    """Core intelligence engine for harvesting, generating, and exporting IT Comtor & BrSE reports."""

    @classmethod
    async def harvest_report_data(
        cls,
        db: AsyncSession,
        project_id: str,
        report_type: str = "client_nippo",
        date_str: Optional[str] = None
    ) -> Dict[str, Any]:
        """Harvests project tasks, blockers, pending Q&As, and meeting decisions for review."""
        if not date_str:
            date_str = datetime.date.today().isoformat()

        # Fetch Project details
        proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        project_name = proj.name if proj else "Dự án IT"

        # Fetch Work Items
        query = select(WorkItem).where(WorkItem.project_id == project_id).order_by(desc(WorkItem.updated_at))
        all_items = (await db.execute(query)).scalars().all()

        now = datetime.datetime.utcnow()
        completed_items = []
        in_progress_items = []
        blocked_items = []
        pending_questions = []

        for item in all_items:
            days_pending = 0
            if item.created_at:
                days_pending = max(0, (now - item.created_at).days)

            item_payload = {
                "id": item.id,
                "req_code": item.req_code or item.id[:8].upper(),
                "title": item.title,
                "description": item.description or "",
                "status": item.status,
                "priority": item.priority or "MEDIUM",
                "assignee": item.assignee or "Team Dev",
                "deadline_date": item.deadline_date,
                "item_type": item.item_type,
                "days_pending": days_pending
            }

            if item.status == "DONE":
                completed_items.append(item_payload)
            elif item.status in ["IN_PROGRESS", "CONFIRMED", "PROPOSED"]:
                in_progress_items.append(item_payload)
            elif item.status == "BLOCKED" or item.is_conflict:
                blocked_items.append(item_payload)

            if item.item_type in ["QUESTION", "OPEN_QUESTION"] and item.status != "DONE":
                pending_questions.append(item_payload)

        # Fetch recent Meeting decisions
        meeting_query = (
            select(MeetingRecord)
            .where(MeetingRecord.project_id == project_id)
            .order_by(desc(MeetingRecord.created_at))
            .limit(3)
        )
        recent_meetings = (await db.execute(meeting_query)).scalars().all()
        recent_decisions = []
        for m in recent_meetings:
            try:
                decs = json.loads(m.decisions_json or "[]")
                for d in decs:
                    if isinstance(d, dict):
                        recent_decisions.append(d.get("decision") or d.get("title") or str(d))
                    elif isinstance(d, str):
                        recent_decisions.append(d)
            except Exception:
                pass

        return {
            "project_id": project_id,
            "project_name": project_name,
            "report_date": date_str,
            "completed_items": completed_items[:15],
            "in_progress_items": in_progress_items[:15],
            "blocked_items": blocked_items[:10],
            "pending_questions": pending_questions[:10],
            "recent_decisions": recent_decisions[:5]
        }

    @classmethod
    async def generate_report(
        cls,
        payload: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Generates multi-channel business report content using LLM with Keigo & Saisoku rules or smart fallback."""
        project_id = payload.get("project_id", "")
        report_type = payload.get("report_type", "client_nippo") # client_nippo, client_shuho, internal_standup
        is_auto_harvest = payload.get("is_auto_harvest", False)
        manual_input_raw = payload.get("manual_input_raw", "").strip()
        target_language = payload.get("target_language", "ja") # ja, vi, bilingual
        sender_name = payload.get("sender_name", "BrSE / Offshore Lead")
        recipient_name = payload.get("recipient_name", "お客様 (Client PM / Tech Lead)")
        selected_item_ids = payload.get("selected_item_ids", [])
        additional_notes = payload.get("additional_notes", "").strip()
        report_date = payload.get("report_date") or datetime.date.today().isoformat()
        template_file_path = payload.get("template_file_path")
        custom_text_template = payload.get("custom_text_template", "").strip()

        provider_name = payload.get("provider", "auto")
        model = payload.get("model")

        # Fetch project and glossary
        proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        project_name = proj.name if proj else "IT Project"

        glossary_items = (await db.execute(
            select(GlossaryTerm).where(
                or_(GlossaryTerm.project_id == project_id, GlossaryTerm.scope == "global")
            ).limit(20)
        )).scalars().all()
        glossary_context = "\n".join([f"- {g.source_term} => {g.target_term}" for g in glossary_items])

        # Prepare Harvest Data if enabled
        harvested_completed = []
        harvested_plans = []
        harvested_questions = []

        if is_auto_harvest and selected_item_ids:
            query = select(WorkItem).where(WorkItem.id.in_(selected_item_ids))
            items = (await db.execute(query)).scalars().all()
            for it in items:
                label = f"[{it.req_code or it.id[:6]}] {it.title}"
                if it.status == "DONE":
                    harvested_completed.append(label)
                elif it.item_type in ["QUESTION", "OPEN_QUESTION"]:
                    harvested_questions.append(label)
                else:
                    harvested_plans.append(label)

        # Build prompt
        prompt = cls._build_report_prompt(
            project_name=project_name,
            report_type=report_type,
            report_date=report_date,
            sender_name=sender_name,
            recipient_name=recipient_name,
            is_auto_harvest=is_auto_harvest,
            manual_input_raw=manual_input_raw,
            harvested_completed=harvested_completed,
            harvested_plans=harvested_plans,
            harvested_questions=harvested_questions,
            additional_notes=additional_notes,
            target_language=target_language,
            glossary_context=glossary_context,
            custom_text_template=custom_text_template
        )

        # Call AI provider
        target_prov = provider_name if provider_name and provider_name != "auto" else "groq"
        provider = provider_registry.get_provider(target_prov) or provider_registry.get_provider("gemini") or provider_registry.get_provider("ollama")

        ai_response_json = None
        if provider:
            try:
                system_instruction = (
                    f"You are a Senior IT BrSE crafting high-stakes software project reports with 100% fidelity to user input. "
                    f"Target Language is strictly {target_language.upper()} (vi = 100% formal Vietnamese, ja = 100% Japanese Business Keigo, bilingual = Japanese + Vietnamese parallel). "
                    f"STRICT FIDELITY RULES: "
                    f"1. ZERO TASK LOSS: Account for 100% of tasks, bullets, and items provided by user. Never drop, skip, or omit any task (e.g. Unit tests, documentation, bug fixes). "
                    f"2. ZERO HALLUCINATION: Never invent fake tasks if the user did not provide future plans. "
                    f"3. INPUT MIRRORING: If user divided input by 'Hôm qua' and 'Hôm nay', output matching sections ('【昨日の実績】' and '【本日の実績】'). "
                    f"4. SEMANTIC ACCURACY: Categorize blockers/Q&A/schedule-status under issues, NOT under completed achievements. "
                    f"5. GREETING: Japanese reports MUST strictly start with 'お疲れ様です。' (never omit 'お')."
                )
                resp = await provider.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=model,
                    temperature=0.25,
                    json_mode=True
                )
                ai_response_json = clean_json_response(resp.text)
            except Exception as e:
                logger.warning(f"AI report generation exception, falling back to rule-based engine: {e}")

        # Fallback if AI fails or offline
        if not ai_response_json or "content_markdown" not in ai_response_json:
            ai_response_json = cls._generate_smart_fallback(
                project_name=project_name,
                report_type=report_type,
                report_date=report_date,
                sender_name=sender_name,
                recipient_name=recipient_name,
                manual_input_raw=manual_input_raw,
                harvested_completed=harvested_completed,
                harvested_plans=harvested_plans,
                harvested_questions=harvested_questions,
                additional_notes=additional_notes,
                target_language=target_language,
                custom_text_template=custom_text_template
            )

        content_markdown = ai_response_json.get("content_markdown", "")
        summary_text = ai_response_json.get("summary_text", "Báo cáo tiến độ công việc" if target_language == "vi" else "本日の進捗状況をご報告いたします。")
        achievements_list = ai_response_json.get("achievements", harvested_completed)
        plans_list = ai_response_json.get("plans", harvested_plans)
        issues_list = ai_response_json.get("issues", harvested_questions)
        vietnamese_preview = ai_response_json.get("content_vietnamese_preview", "")

        # Multi-Channel Formatters
        content_html = cls.render_rich_text_html(content_markdown, report_type, project_name, report_date, sender_name)
        content_chatwork = cls.render_chatwork_tags(content_markdown, report_type, project_name, report_date, sender_name)
        content_slack = cls.render_slack_mrkdwn(content_markdown)

        # Save to database
        if target_language == "vi":
            title_prefix = "【Báo cáo ngày】" if report_type == "client_nippo" else ("【Báo cáo tuần】" if report_type == "client_shuho" else "【Standup】")
        else:
            title_prefix = "【日報】" if report_type == "client_nippo" else ("【週報】" if report_type == "client_shuho" else "【Standup】")
        report_title = f"{title_prefix} {project_name} — {report_date}"

        record = ReportRecord(
            project_id=project_id,
            report_type=report_type,
            title=report_title,
            report_date=report_date,
            recipient_name=recipient_name,
            sender_name=sender_name,
            is_auto_harvest=is_auto_harvest,
            manual_input_raw=manual_input_raw,
            target_language=target_language,
            template_file_path=template_file_path,
            content_markdown=content_markdown,
            content_html=content_html,
            content_chatwork=content_chatwork,
            content_slack=content_slack,
            content_vietnamese_preview=vietnamese_preview,
            raw_items_json=json.dumps(selected_item_ids)
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        return {
            "id": record.id,
            "project_id": record.project_id,
            "title": record.title,
            "report_type": record.report_type,
            "report_date": record.report_date,
            "recipient_name": record.recipient_name,
            "sender_name": record.sender_name,
            "target_language": record.target_language,
            "content_markdown": record.content_markdown,
            "content_html": record.content_html,
            "content_chatwork": record.content_chatwork,
            "content_slack": record.content_slack,
            "content_vietnamese_preview": record.content_vietnamese_preview,
            "achievements": achievements_list,
            "plans": plans_list,
            "issues": issues_list,
            "summary_text": summary_text,
            "created_at": record.created_at.isoformat()
        }

    @classmethod
    def _build_report_prompt(
        cls,
        project_name: str,
        report_type: str,
        report_date: str,
        sender_name: str,
        recipient_name: str,
        is_auto_harvest: bool,
        manual_input_raw: str,
        harvested_completed: List[str],
        harvested_plans: List[str],
        harvested_questions: List[str],
        additional_notes: str,
        target_language: str,
        glossary_context: str,
        custom_text_template: str = ""
    ) -> str:
        """Constructs an expert Japanese Business Keigo report prompt with Saisoku etiquette."""
        report_type_label = (
            "日報 (Daily Progress Report to Client)" if report_type == "client_nippo"
            else ("週報 (Weekly Progress Report to Client & Executive)" if report_type == "client_shuho"
                  else "社内日報 / Daily Standup (Internal Vietnamese Report)")
        )

        manual_section = f"Manual Input Tasks (from User):\n{manual_input_raw}" if manual_input_raw else "(No manual tasks provided)"
        harvested_sec = ""
        if is_auto_harvest:
            harvested_sec = f"""
Harvested System Data:
- Completed items: {json.dumps(harvested_completed, ensure_ascii=False)}
- Planned items: {json.dumps(harvested_plans, ensure_ascii=False)}
- Questions waiting for client confirmation (Saisoku targets): {json.dumps(harvested_questions, ensure_ascii=False)}
"""
        else:
            harvested_sec = "(Auto-harvest is OFF. Strictly base report on Manual Input Tasks)"

        custom_template_prompt = ""
        if custom_text_template:
            custom_template_prompt = f"""
================================================================================
4. HIGHEST PRIORITY OVERRIDE - USER'S CUSTOM TEXT FORMAT TEMPLATE:
The user has provided an exact report format template below.
YOU MUST STRICTLY OVERRIDE ANY DEFAULT GREETINGS, DEFAULT SECTION HEADERS, AND DEFAULT STRUCTURES.
Do NOT use 'Kính gửi...' or standard headers unless they are in the custom template!
The final 'content_markdown' MUST strictly follow the exact wrapper, section titles, headers, bullet style,
special channel tags (e.g. Chatwork [info][title]...[/title][/info], [hr], Slack mrkdwn, or signatures),
and salutation/closing style of the custom template below.
Extract the new tasks and progress from the INPUT DATA and populate them into the corresponding sections of this template.
Do NOT lose the surrounding formatting, tags, or structure!

--- BEGIN CUSTOM TEMPLATE ---
{custom_text_template}
--- END CUSTOM TEMPLATE ---
================================================================================
"""

        # Tailor instructions strictly based on requested target_language
        if target_language == "vi":
            lang_specific_rules = f"""
TARGET LANGUAGE MANDATE: 100% VIETNAMESE (TIẾNG VIỆT CÔNG SỞ TRANG TRỌNG).
- ALL sections, greetings, bullet points, and headers MUST be written in natural, highly professional Vietnamese.
- GREETING: "Kính gửi {recipient_name},\nTôi là {sender_name} (BrSE / Offshore Lead).\n\nTôi xin phép báo cáo tiến độ công việc dự án {project_name} (ngày {report_date}) như sau:"
- STRUCTURE:
  ### 【1. Các hạng mục công việc đã hoàn thành】
  (Gạch đầu dòng rõ ràng, nêu bật tiến độ và kết quả)
  ### 【2. Kế hoạch công việc tiếp theo】
  (Các task dự kiến ngày mai / tuần tới, milestone tiếp theo)
  ### 【3. Vấn đề vướng mắc & Cần xác nhận】
  (Nhắc nhở lịch sự các câu hỏi tồn đọng hoặc tài liệu chờ phía khách hàng confirm)
  ### 【4. Ghi chú & Thông báo khác】
  (Lịch nghỉ, release, lưu ý kỹ thuật nếu có)
- CLOSING: "Trân trọng cảm ơn sự phối hợp và hỗ trợ của Quý khách hàng/Đối tác! Chúc Quý khách hàng một ngày làm việc hiệu quả."
- Do NOT output Japanese in content_markdown or JSON fields when target_language is 'vi'. Everything must be professional Vietnamese.
"""
            json_schema_desc = """{
  "summary_text": "Tóm tắt tiến độ 1 câu ngắn gọn bằng tiếng Việt",
  "achievements": ["Hạng mục 1 đã hoàn thành", "Hạng mục 2 đã hoàn thành"],
  "plans": ["Kế hoạch 1 tiếp theo", "Kế hoạch 2"],
  "issues": ["Vấn đề / Câu hỏi chờ confirm 1", "Vấn đề 2"],
  "content_markdown": "Bản báo cáo hoàn chỉnh 100% bằng Tiếng Việt với lời chào, tiêu đề và gạch đầu dòng",
  "content_vietnamese_preview": "Bản dịch tóm tắt hoặc nội dung báo cáo tiếng Việt"
}"""
        elif target_language == "bilingual":
            lang_specific_rules = f"""
TARGET LANGUAGE MANDATE: BILINGUAL (JAPANESE KEIGO + VIETNAMESE PARALLEL).
- Provide Japanese Business Keigo first, followed by clear Vietnamese parallel explanation for each section.
- Perfect for Comtors/BrSE communicating with both Japanese clients and Vietnamese internal managers.
"""
            json_schema_desc = """{
  "summary_text": "One-sentence high level summary in Japanese / Tiếng Việt",
  "achievements": ["Task 1 (JP + VI)", "Task 2 (JP + VI)"],
  "plans": ["Next task 1 (JP + VI)", "Next task 2"],
  "issues": ["Issue / question 1 with polite reminder", "Issue 2"],
  "content_markdown": "Full formatted bilingual report in Markdown",
  "content_vietnamese_preview": "Bản dịch tóm tắt tiếng Việt đối chiếu"
}"""
        else:
            lang_specific_rules = f"""
TARGET LANGUAGE MANDATE: 100% JAPANESE BUSINESS KEIGO (丁寧語・謙譲語).
- GREETING: Must ALWAYS strictly start with:
  お疲れ様です。{recipient_name}様
  {sender_name}です。

  本日の進捗状況をご報告いたします。
  (CRITICAL: The greeting MUST begin with "お疲れ様です。" - never drop the "お"!).

- DYNAMIC SECTION MAPPING (INPUT SAO OUTPUT VẬY):
  - If the user's input has distinct temporal sections like 'Hôm qua:' and 'Hôm nay:' (or Yesterday/Today):
    OUTPUT MUST MIRROR BOTH SECTIONS:
    ### 【昨日の実績】
    - (Translate and include ALL tasks listed under 'Hôm qua')
    ### 【本日の実績】
    - (Translate and include ALL tasks listed under 'Hôm nay')
  - If user did NOT specify distinct sections:
    ### 【本日の実績】
    - (Translate and include all completed/current tasks)

- ZERO HALLUCINATION FOR FUTURE PLANS:
  - If the user did NOT provide any planned tasks for tomorrow, DO NOT invent fake tasks!
  - You may either omit 【明日の予定】 or simply state:
    ### 【明日の予定】
    - 予定通りのマイルストーンを推進いたします。
  - NEVER invent fake module names, tasks, or promises the user never wrote!

- SEMANTIC SEGREGATION (BLOCKERS & QUESTIONS):
  - Items about waiting for client confirmation (e.g. 'QA-021 đang chờ khách xác nhận...'), blockers, or schedule status ('Chưa có issue ảnh hưởng schedule') MUST be placed under:
    ### 【課題・ご確認のお願い】
    - (Polite Saisoku for client confirmation items, and note that current schedule has no blocking issues)
  - NEVER put pending Q&A or 'no issues' statements under 【本日の実績】!

- CLOSING:
  引き続きよろしくお願いいたします。
"""
            json_schema_desc = """{
  "summary_text": "One-sentence high level summary in Japanese",
  "achievements": ["Task 1 title/summary", "Task 2 title/summary"],
  "plans": ["Next task 1", "Next task 2"],
  "issues": ["Issue / question 1 with polite reminder", "Issue 2"],
  "content_markdown": "Full formatted report in Markdown with headers, bullet points, and greetings",
  "content_vietnamese_preview": "Bản dịch tóm tắt hoặc giải thích tiếng Việt cho BrSE/Comtor đối chiếu"
}"""

        return f"""You are an elite IT BrSE and Project Manager communicating with Japanese/Vietnamese clients.
Generate a structured, professional, culturally flawless {report_type_label}.

PROJECT CONTEXT:
- Project: {project_name}
- Date: {report_date}
- Sender (Offshore Lead/BrSE): {sender_name}
- Recipient: {recipient_name}
- Target Language: {target_language} (ja = Japanese, vi = Vietnamese, bilingual = Japanese + Vietnamese)
- Additional Notes: {additional_notes or "None"}

PROJECT GLOSSARY & MANDATORY TERMS:
{glossary_context if glossary_context else "(No project specific terms)"}

INPUT DATA:
{manual_section}
{harvested_sec}
CRITICAL RULES:
1. INPUT NORMALIZATION (MIXED LANGUAGE SUPPORT):
   - The user's input may be a raw, unstructured, chaotic mix of Vietnamese, Japanese, and English (e.g. 'đã fix bug 画面 ログイン, đang test 決済, cần khách confirm 割引仕様').
   - You MUST intelligently decipher, de-duplicate, synthesize, and categorize all tasks.
   - You MUST translate and harmonize ALL items into the requested Target Language ({target_language}) with natural, professional grammar and technical terms. Do NOT leave raw mixed language fragments.
2. ZERO TASK LOSS (BẢO TOÀN 100% TASK - CỰC KỲ QUAN TRỌNG):
   - You MUST account for EVERY task, bullet point, and item in the user's input.
   - Do NOT drop, skip, or merge away any task (e.g. Unit tests, documentation, bug fixes, deployment). If the user provided 6 items, ALL 6 items must be present!
3. ZERO HALLUCINATION (TUYỆT ĐỐI KHÔNG TỰ Ý BỊA TASK):
   - Do NOT invent fake tasks for tomorrow or any other section that the user never mentioned.
4. INPUT MIRRORING (INPUT NHƯ NÀO OUTPUT NHƯ VẬY):
   - If user grouped input by 'Hôm qua' and 'Hôm nay', output '【昨日の実績】' and '【本日の実績】'.
5. POLITE SAISOKU (催促):
   - If there are open questions or pending specs, formulate them respectfully under the issues/confirmations section. Never blame the client.
{lang_specific_rules}
{custom_template_prompt}

Return STRICT JSON matching:
{json_schema_desc}"""

    @classmethod
    def _generate_smart_fallback(
        cls,
        project_name: str,
        report_type: str,
        report_date: str,
        sender_name: str,
        recipient_name: str,
        manual_input_raw: str,
        harvested_completed: List[str],
        harvested_plans: List[str],
        harvested_questions: List[str],
        additional_notes: str,
        target_language: str,
        custom_text_template: str = ""
    ) -> Dict[str, Any]:
        """Provides instant high-quality template response even if AI provider is unreachable."""
        # Section-aware parser with Zero Task Loss
        yesterday_items: List[str] = []
        today_items: List[str] = []
        planned_items: List[str] = []
        issues_items: List[str] = list(harvested_questions)
        general_tasks: List[str] = list(harvested_completed)

        current_section = "general"
        for raw_line in manual_input_raw.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_lower = line.lower()

            # Detect section headers
            if any(k in line_lower for k in ["hôm qua", "yesterday", "昨日"]):
                current_section = "yesterday"
                continue
            elif any(k in line_lower for k in ["hôm nay", "today", "本日"]):
                current_section = "today"
                continue
            elif any(k in line_lower for k in ["ngày mai", "tomorrow", "kế hoạch", "予定"]):
                current_section = "plans"
                continue
            elif any(k in line_lower for k in ["vấn đề", "issue", "blocker", "cần xác nhận", "課題"]):
                current_section = "issues"
                continue

            clean_text = line.strip("-*• \t")
            if not clean_text:
                continue

            clean_lower = clean_text.lower()
            # Detect if this specific item is an issue / question / schedule note
            is_issue = any(k in clean_lower for k in [
                "chờ khách", "confirm", "xác nhận", "qa-", "q&a", "blocker",
                "chưa có issue", "ảnh hưởng schedule", "vướng mắc", "rủi ro"
            ]) or any(k in clean_text for k in ["課題", "確認", "保留", "リスク"])

            if is_issue:
                issues_items.append(clean_text)
            elif current_section == "yesterday":
                yesterday_items.append(clean_text)
            elif current_section == "today":
                today_items.append(clean_text)
            elif current_section == "plans":
                planned_items.append(clean_text)
            else:
                general_tasks.append(clean_text)

        if not issues_items:
            issues_items = ["Hiện tại không có blocker nghiêm trọng nào ảnh hưởng tới tiến độ." if target_language == "vi" else "現在、ブロッカーとなる重大な課題は発生しておりません。"]

        # Aggregate achievements
        all_achievements = yesterday_items + today_items + general_tasks
        if not all_achievements:
            all_achievements = ["Hoàn thành các task phát triển và kiểm thử theo tiến độ." if target_language == "vi" else "予定されていたタスクの実装およびコードレビューを順調に完了。"]

        # Aggregate plans (Zero hallucination: do NOT invent fake tasks if user didn't write any)
        plans = harvested_plans + planned_items
        if not plans:
            plans = ["Tiếp tục triển khai các module và test case theo đúng kế hoạch." if target_language == "vi" else "予定通りのマイルストーンを推進いたします。"]

        # Formatting strings
        yesterday_str = "\n".join([f"- {y}" for y in yesterday_items])
        today_str = "\n".join([f"- {t}" for t in today_items])
        achievements_str = "\n".join([f"- {a}" for a in all_achievements])
        plans_str = "\n".join([f"- {p}" for p in plans])
        issues_str = "\n".join([f"- {i}" for i in issues_items])

        # If user supplied custom_text_template, use it as base
        if custom_text_template:
            templated_md = custom_text_template
            for ph, val in [
                ("{{title}}", f"Báo cáo tiến độ {project_name} — {report_date}"),
                ("{{project_name}}", project_name),
                ("{{date}}", report_date),
                ("{{sender}}", sender_name),
                ("{{recipient}}", recipient_name),
                ("{{achievements}}", achievements_str),
                ("{{hoàn_thành}}", achievements_str),
                ("{{plans}}", plans_str),
                ("{{kế_hoạch}}", plans_str),
                ("{{issues}}", issues_str),
                ("{{vấn_đề}}", issues_str),
                ("{{notes}}", additional_notes or "None"),
            ]:
                if ph in templated_md:
                    templated_md = templated_md.replace(ph, val)

            return {
                "summary_text": f"Báo cáo tiến độ {project_name} theo mẫu định dạng tùy chỉnh.",
                "achievements": all_achievements,
                "plans": plans,
                "issues": issues_items,
                "content_markdown": templated_md,
                "content_vietnamese_preview": templated_md
            }

        if target_language == "vi":
            if yesterday_items and today_items:
                md = f"""Kính gửi {recipient_name},
Tôi là {sender_name} (BrSE / Offshore Lead).

Tôi xin phép gửi báo cáo tiến độ công việc ngày {report_date} như sau:

### 【1. Các hạng mục hôm qua】
{yesterday_str}

### 【2. Các hạng mục hôm nay】
{today_str}

### 【3. Vấn đề vướng mắc & Cần xác nhận】
{issues_str}

### 【4. Ghi chú & Thông tin khác】
{additional_notes if additional_notes else "Không có ghi chú đặc biệt."}

Trân trọng cảm ơn sự phối hợp của Quý khách hàng/Đối tác!
"""
                vi_prev = md
                summary_text = f"Báo cáo tiến độ công việc ngày {report_date} của dự án {project_name}."
            elif report_type == "client_nippo":
                md = f"""Kính gửi {recipient_name},
Tôi là {sender_name} (BrSE / Offshore Lead).

Tôi xin phép gửi báo cáo tiến độ công việc ngày {report_date} như sau:

### 【1. Các hạng mục công việc đã hoàn thành】
{achievements_str}

### 【2. Kế hoạch công việc ngày mai】
{plans_str}

### 【3. Vấn đề vướng mắc & Cần xác nhận】
{issues_str}

### 【4. Ghi chú & Thông tin khác】
{additional_notes if additional_notes else "Không có ghi chú đặc biệt."}

Trân trọng cảm ơn sự phối hợp của Quý khách hàng/Đối tác!
"""
                vi_prev = md
                summary_text = f"Báo cáo tiến độ công việc ngày {report_date} của dự án {project_name}."
            elif report_type == "client_shuho":
                md = f"""Kính gửi {recipient_name},
Tôi là {sender_name} (BrSE / Offshore Lead).

Tôi xin phép gửi báo cáo tổng kết tiến độ tuần và kế hoạch tuần tới (ngày {report_date}) của dự án {project_name}:

### 【1. Tóm tắt tiến độ tuần】
Đội ngũ phát triển đã hoàn thành các mục tiêu chính trong tuần theo đúng kế hoạch đề ra.

### 【2. Các hạng mục công việc đã hoàn thành】
{achievements_str}

### 【3. Kế hoạch công việc & Mục tiêu tuần tới】
{plans_str}

### 【4. Vấn đề, Rủi ro & Cần đối tác phản hồi】
{issues_str}

### 【5. Ghi chú & Thông tin khác】
{additional_notes if additional_notes else "Không có ghi chú đặc biệt."}

Kính chúc Quý khách hàng/Đối tác tuần làm việc hiệu quả và thành công!
"""
                vi_prev = md
                summary_text = f"Báo cáo tổng kết tuần và kế hoạch tuần tới của dự án {project_name}."
            else: # internal_standup
                md = f"""## 🇻🇳 Báo cáo Daily Standup — {project_name} ({report_date})
**Người báo cáo:** {sender_name}

### ✅ 1. Công việc đã hoàn thành:
{achievements_str}

### ⏳ 2. Kế hoạch tiếp theo:
{plans_str}

### ⚠️ 3. Vướng mắc / Cần hỗ trợ (Blockers):
{issues_str}

### 📝 4. Ghi chú thêm:
{additional_notes if additional_notes else "Không có."}
"""
                vi_prev = md
                summary_text = f"Standup nội bộ {project_name} ngày {report_date}."

            return {
                "summary_text": summary_text,
                "achievements": all_achievements,
                "plans": plans,
                "issues": issues_items,
                "content_markdown": md,
                "content_vietnamese_preview": vi_prev
            }

        # Japanese / Bilingual Fallback
        if report_type == "client_nippo":
            if yesterday_items and today_items:
                sections_part = f"""### 【昨日の実績】
{yesterday_str}

### 【本日の実績】
{today_str}"""
            else:
                sections_part = f"""### 【本日の実績】
{achievements_str}"""

            plans_part = f"""### 【明日の作業予定】
{plans_str}
""" if planned_items else ""

            md = f"""お疲れ様です。{recipient_name}様
{sender_name}です。

本日の進捗状況をご報告いたします。

{sections_part}

{plans_part}### 【課題・ご確認のお願い】
{issues_str}

### 【ご連絡事項】
{additional_notes if additional_notes else "特記事項はございません。"}

引き続きよろしくお願いいたします。
"""
            vi_prev = f"""Báo cáo ngày {report_date}: Đã hoàn thành các hạng mục phát triển theo kế hoạch. Kế hoạch tiếp theo tiếp tục đẩy mạnh tiến độ và theo dõi các điểm cần làm rõ với khách hàng."""
        elif report_type == "client_shuho":
            md = f"""お疲れ様です。{recipient_name}様
{sender_name}です。

今週の進捗状況および来週の作業計画をご報告いたします。

### 【今週の進捗サマリー】
今週予定しておりましたマイルストーンについて、開発チーム一同順調に対応を進めております。

### 【主要な対応実績】
{achievements_str}

### 【来週の作業計画 & 直近マイルストーン】
{plans_str}

### 【課題・リスク管理 & ご確認事項】
{issues_str}

### 【その他・ご連絡事項】
{additional_notes if additional_notes else "特記事項はございません。"}

来週も何卒よろしくお願い申し上げます。
"""
            vi_prev = f"""Báo cáo tuần {report_date}: Hoàn thành các tính năng chính trong tuần. Tuần tới tập trung test và xử lý các vấn đề tồn đọng."""
        else: # internal_standup
            md = f"""## 🇻🇳 Báo cáo Daily Standup — {project_name} ({report_date})
**Người báo cáo:** {sender_name}

### ✅ 1. Công việc đã hoàn thành:
{achievements_str}

### ⏳ 2. Kế hoạch tiếp theo:
{plans_str}

### ⚠️ 3. Vướng mắc / Cần hỗ trợ (Blockers):
{issues_str}

### 📝 4. Ghi chú thêm:
{additional_notes if additional_notes else "Không có."}
"""
            vi_prev = md

        return {
            "summary_text": f"{project_name}の進捗状況をご報告いたします。",
            "achievements": achievements,
            "plans": plans,
            "issues": issues,
            "content_markdown": md,
            "content_vietnamese_preview": vi_prev
        }

    # =========================================================================
    # MULTI-CHANNEL FORMATTERS
    # =========================================================================
    @classmethod
    def render_rich_text_html(
        cls,
        markdown_text: str,
        report_type: str,
        project_name: str,
        report_date: str,
        sender_name: str
    ) -> str:
        """
        Generates production-grade inline CSS HTML compatible with Microsoft Outlook and Gmail clipboard pasting.
        When pasted, fonts, colors, line heights, and bullet indentations remain pixel-perfect.
        """
        html_lines = []
        for line in markdown_text.splitlines():
            line_str = line.strip()
            if not line_str:
                html_lines.append("<p style='margin: 8px 0;'>&nbsp;</p>")
                continue
            
            if line_str.startswith("### "):
                header_title = line_str.replace("### ", "").strip()
                html_lines.append(
                    f"<h3 style='margin: 16px 0 8px 0; font-size: 15px; font-weight: bold; color: #1e3a8a; "
                    f"border-bottom: 2px solid #bfdbfe; padding-bottom: 4px;'>{header_title}</h3>"
                )
            elif line_str.startswith("## "):
                header_title = line_str.replace("## ", "").strip()
                html_lines.append(
                    f"<h2 style='margin: 18px 0 10px 0; font-size: 17px; font-weight: bold; color: #0f172a; "
                    f"border-left: 4px solid #2563eb; padding-left: 8px;'>{header_title}</h2>"
                )
            elif line_str.startswith("- ") or line_str.startswith("• "):
                bullet_content = line_str[2:].strip()
                # Highlight bold text
                bullet_content = cls._convert_md_bold(bullet_content)
                html_lines.append(
                    f"<li style='margin: 4px 0 4px 20px; line-height: 1.6; color: #334155;'>{bullet_content}</li>"
                )
            else:
                body_content = cls._convert_md_bold(line_str)
                html_lines.append(
                    f"<p style='margin: 4px 0; line-height: 1.6; color: #1e293b;'>{body_content}</p>"
                )

        body_html = "\n".join(html_lines)
        return (
            f"<div style='font-family: Meiryo, \"Yu Gothic\", \"Segoe UI\", Helvetica, Arial, sans-serif; "
            f"font-size: 14px; line-height: 1.6; color: #1e293b; max-width: 720px;'>"
            f"{body_html}"
            f"</div>"
        )

    @classmethod
    def _convert_md_bold(cls, text: str) -> str:
        """Converts **bold** markdown to <b> tags."""
        import re
        return re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)

    @classmethod
    def render_chatwork_tags(
        cls,
        markdown_text: str,
        report_type: str,
        project_name: str,
        report_date: str,
        sender_name: str
    ) -> str:
        """Transforms report content into native Chatwork [info][title]...[/title][/info] BBCode tags."""
        title_tag = "日報" if report_type == "client_nippo" else ("週報" if report_type == "client_shuho" else "Daily Standup")
        
        cw_lines = []
        cw_lines.append(f"[info][title]【{title_tag}】{project_name} — {report_date}（{sender_name}）[/title]")
        
        in_list = False
        for line in markdown_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("### ") or line_str.startswith("## "):
                h = line_str.replace("### ", "").replace("## ", "").strip()
                cw_lines.append(f"\n[hr]\n[b]{h}[/b]")
            elif line_str.startswith("- ") or line_str.startswith("• "):
                cw_lines.append(f"・{line_str[2:].strip()}")
            else:
                cw_lines.append(line_str)

        cw_lines.append("[/info]")
        return "\n".join(cw_lines)

    @classmethod
    def render_slack_mrkdwn(cls, markdown_text: str) -> str:
        """Cleans and standardizes markdown for Slack / Microsoft Teams block pasting with emoji cues."""
        slack_lines = []
        for line in markdown_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("### 【本日の実績】") or line_str.startswith("### 【今週の主要な対応実績】"):
                slack_lines.append("\n:white_check_mark: *" + line_str.replace("### ", "") + "*")
            elif line_str.startswith("### 【明日の作業予定】") or line_str.startswith("### 【来週の作業計画"):
                slack_lines.append("\n:calendar: *" + line_str.replace("### ", "") + "*")
            elif line_str.startswith("### 【課題・ご確認のお願い】") or line_str.startswith("### 【課題・リスク管理"):
                slack_lines.append("\n:warning: *" + line_str.replace("### ", "") + "*")
            elif line_str.startswith("### ") or line_str.startswith("## "):
                slack_lines.append("\n:memo: *" + line_str.replace("### ", "").replace("## ", "") + "*")
            else:
                slack_lines.append(line)
        return "\n".join(slack_lines)

    # =========================================================================
    # DOCUMENT EXPORTERS (.docx, .xlsx, .pptx)
    # =========================================================================
    @classmethod
    def fill_docx_template(
        cls,
        template_path: str,
        report_data: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        Clones an existing Word template (.docx) and replaces placeholders and section bullets,
        preserving corporate headers, footers, branding, tables, and typography.
        """
        import docx

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"DOCX template not found: {template_path}")

        doc = docx.Document(template_path)

        project_name = report_data.get("project_name", "IT Project")
        report_title = report_data.get("title", "進捗報告書")
        report_date = report_data.get("report_date", "")
        sender_name = report_data.get("sender_name", "BrSE / Offshore Team")
        recipient_name = report_data.get("recipient_name", "お客様 (Client)")
        target_language = report_data.get("target_language", "ja")
        is_vi = target_language == "vi"

        achievements = report_data.get("achievements", [])
        plans = report_data.get("plans", [])
        issues = report_data.get("issues", [])
        summary_text = report_data.get("summary_text", "")

        achievements_str = "\n".join([f"• {a}" for a in achievements]) if achievements else ("• Đã hoàn thành các hạng mục theo kế hoạch." if is_vi else "• 計画通り順調に進捗しております。")
        plans_str = "\n".join([f"• {p}" for p in plans]) if plans else ("• Tiếp tục triển khai các mục tiêu tiếp theo." if is_vi else "• 予定通りのマイルストーンを推進いたします。")
        issues_str = "\n".join([f"• {i}" for i in issues]) if issues else ("• Hiện tại không có blocker nghiêm trọng." if is_vi else "• 現在、ブロッカーとなる重大な課題はございません。")

        replacements = {
            "{{title}}": report_title,
            "{{tiêu_đề}}": report_title,
            "{{tiêu đề}}": report_title,
            "{{project_name}}": project_name,
            "{{dự_án}}": project_name,
            "{{dự án}}": project_name,
            "{{date}}": report_date,
            "{{ngày}}": report_date,
            "{{ngày báo cáo}}": report_date,
            "{{sender}}": sender_name,
            "{{người_gửi}}": sender_name,
            "{{người báo cáo}}": sender_name,
            "{{recipient}}": recipient_name,
            "{{người_nhận}}": recipient_name,
            "{{khách hàng}}": recipient_name,
            "{{achievements}}": achievements_str,
            "{{hoàn_thành}}": achievements_str,
            "{{thành tựu}}": achievements_str,
            "{{plans}}": plans_str,
            "{{kế_hoạch}}": plans_str,
            "{{issues}}": issues_str,
            "{{vấn_đề}}": issues_str,
            "{{summary}}": summary_text,
            "{{tóm_tắt}}": summary_text,
        }

        def replace_in_text(text: str) -> str:
            for k, v in replacements.items():
                if k in text:
                    text = text.replace(k, v)
                if k.upper() in text:
                    text = text.replace(k.upper(), v)
            return text

        # 1. Replace in paragraphs
        for p in doc.paragraphs:
            if any(k in p.text or k.upper() in p.text for k in replacements):
                p.text = replace_in_text(p.text)

        # 2. Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        if any(k in p.text or k.upper() in p.text for k in replacements):
                            p.text = replace_in_text(p.text)

        # 3. Replace in headers / footers
        for section in doc.sections:
            for header_p in section.header.paragraphs:
                if any(k in header_p.text or k.upper() in header_p.text for k in replacements):
                    header_p.text = replace_in_text(header_p.text)
            for footer_p in section.footer.paragraphs:
                if any(k in footer_p.text or k.upper() in footer_p.text for k in replacements):
                    footer_p.text = replace_in_text(footer_p.text)

        dirname = os.path.dirname(output_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        doc.save(output_path)
        logger.info(f"DOCX report cloned & filled into {output_path}")
        return output_path

    @classmethod
    def export_report_docx(cls, report: ReportRecord, output_path: str) -> str:
        """Generates a styled Microsoft Word (.docx) document or clones template."""
        if report.template_file_path and os.path.exists(report.template_file_path) and report.template_file_path.lower().endswith(".docx"):
            report_data = {
                "title": report.title,
                "project_name": report.title.split("—")[0].strip(),
                "report_date": report.report_date,
                "sender_name": report.sender_name or "BrSE / Offshore Team",
                "recipient_name": report.recipient_name or "お客様",
                "target_language": getattr(report, "target_language", "ja") or "ja",
                "achievements": [],
                "plans": [],
                "issues": [],
                "summary_text": report.content_vietnamese_preview or ""
            }
            current_cat = None
            for line in report.content_markdown.splitlines():
                line_str = line.strip()
                line_lower = line_str.lower()
                if "実績" in line_str or "hoàn thành" in line_lower or "kết quả" in line_lower:
                    current_cat = "achievements"
                elif "予定" in line_str or "計画" in line_str or "kế hoạch" in line_lower or "tiếp theo" in line_lower:
                    current_cat = "plans"
                elif "課題" in line_str or "確認" in line_str or "リスク" in line_str or "vấn đề" in line_lower or "vướng mắc" in line_lower:
                    current_cat = "issues"
                elif (line_str.startswith("- ") or line_str.startswith("• ")) and current_cat:
                    report_data[current_cat].append(line_str[2:].strip())
            return cls.fill_docx_template(report.template_file_path, report_data, output_path)

        import docx
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = docx.Document()

        # Page margins
        for section in doc.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.9)
            section.right_margin = Inches(0.9)

        # Title
        p_title = doc.add_paragraph()
        run_title = p_title.add_run(report.title)
        run_title.font.name = "Meiryo"
        run_title.font.size = Pt(18)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(30, 58, 138) # Navy

        # Meta
        p_meta = doc.add_paragraph()
        p_meta.paragraph_format.space_after = Pt(14)
        run_meta = p_meta.add_run(f"報告日: {report.report_date}  |  宛先: {report.recipient_name or 'お客様'}  |  報告者: {report.sender_name or 'BrSE'}")
        run_meta.font.name = "Meiryo"
        run_meta.font.size = Pt(10)
        run_meta.font.color.rgb = RGBColor(100, 116, 139)

        # Body parsing
        for line in report.content_markdown.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("### ") or line_str.startswith("## "):
                header = line_str.replace("### ", "").replace("## ", "")
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(12)
                p.paragraph_format.space_after = Pt(4)
                r = p.add_run(header)
                r.font.name = "Meiryo"
                r.font.size = Pt(13)
                r.font.bold = True
                r.font.color.rgb = RGBColor(37, 99, 235)
            elif line_str.startswith("- ") or line_str.startswith("• "):
                bullet = line_str[2:].strip()
                p = doc.add_paragraph(style='List Bullet')
                p.paragraph_format.space_after = Pt(3)
                r = p.add_run(bullet)
                r.font.name = "Meiryo"
                r.font.size = Pt(11)
            else:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                r = p.add_run(line_str)
                r.font.name = "Meiryo"
                r.font.size = Pt(11)

        dirname = os.path.dirname(output_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        doc.save(output_path)
        logger.info(f"Report exported to Word (.docx) at {output_path}")
        return output_path

    @classmethod
    def export_report_xlsx(cls, report: ReportRecord, output_path: str) -> str:
        """Generates a Microsoft Excel (.xlsx) workbook with a Summary sheet and Task Item sheet."""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "進捗報告サマリー"

        # Styling definitions
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Meiryo", size=11, bold=True, color="FFFFFF")
        section_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
        section_font = Font(name="Meiryo", size=11, bold=True, color="0369A1")
        cell_font = Font(name="Meiryo", size=10)
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        # Title Block
        ws.merge_cells("A1:D1")
        ws["A1"] = report.title
        ws["A1"].font = Font(name="Meiryo", size=15, bold=True, color="0F172A")
        ws["A1"].alignment = Alignment(vertical="center")

        ws["A2"] = f"報告日: {report.report_date}"
        ws["B2"] = f"宛先: {report.recipient_name or 'お客様'}"
        ws["C2"] = f"報告者: {report.sender_name or 'BrSE'}"
        for col in ["A2", "B2", "C2"]:
            ws[col].font = Font(name="Meiryo", size=10, color="64748B")

        # Table Header
        ws["A4"] = "No."
        ws["B4"] = "区分 (Section)"
        ws["C4"] = "報告内容 (Details)"
        ws["D4"] = "ステータス・備考"
        for col in ["A4", "B4", "C4", "D4"]:
            ws[col].fill = header_fill
            ws[col].font = header_font
            ws[col].alignment = Alignment(horizontal="center", vertical="center")

        current_row = 5
        current_section = "全般"
        item_counter = 1

        for line in report.content_markdown.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("### ") or line_str.startswith("## "):
                current_section = line_str.replace("### ", "").replace("## ", "")
            elif line_str.startswith("- ") or line_str.startswith("• "):
                bullet = line_str[2:].strip()
                ws.cell(row=current_row, column=1, value=item_counter).font = cell_font
                ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="center")
                ws.cell(row=current_row, column=2, value=current_section).font = cell_font
                ws.cell(row=current_row, column=3, value=bullet).font = cell_font
                ws.cell(row=current_row, column=4, value="順調" if "実績" in current_section else ("対応予定" if "予定" in current_section else "確認中")).font = cell_font
                
                for c in range(1, 5):
                    ws.cell(row=current_row, column=c).border = thin_border
                
                current_row += 1
                item_counter += 1

        # Adjust Column Widths
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 65
        ws.column_dimensions["D"].width = 18

        dirname = os.path.dirname(output_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        wb.save(output_path)
        logger.info(f"Report exported to Excel (.xlsx) at {output_path}")
        return output_path

    @classmethod
    def export_report_pptx(cls, report: ReportRecord, output_path: str) -> str:
        """Generates or fills a PowerPoint (.pptx) presentation from the saved report."""
        report_data = {
            "title": report.title,
            "project_name": report.title.split("—")[0].strip(),
            "report_date": report.report_date,
            "sender_name": report.sender_name or "BrSE / Offshore Team",
            "recipient_name": report.recipient_name or "お客様",
            "target_language": getattr(report, "target_language", "ja") or "ja",
            "achievements": [],
            "plans": [],
            "issues": [],
            "summary_text": report.content_vietnamese_preview or "進捗状況をご報告いたします。"
        }

        # Parse bullets from markdown supporting both JP and VI keywords
        current_cat = None
        for line in report.content_markdown.splitlines():
            line_str = line.strip()
            line_lower = line_str.lower()
            if "実績" in line_str or "hoàn thành" in line_lower or "kết quả" in line_lower:
                current_cat = "achievements"
            elif "予定" in line_str or "計画" in line_str or "kế hoạch" in line_lower or "tiếp theo" in line_lower:
                current_cat = "plans"
            elif "課題" in line_str or "確認" in line_str or "リスク" in line_str or "vấn đề" in line_lower or "vướng mắc" in line_lower:
                current_cat = "issues"
            elif (line_str.startswith("- ") or line_str.startswith("• ")) and current_cat:
                report_data[current_cat].append(line_str[2:].strip())

        if report.template_file_path and os.path.exists(report.template_file_path):
            return SlideReportService.fill_slide_template(report.template_file_path, report_data, output_path)
        else:
            return SlideReportService.generate_default_weekly_slide(report_data, output_path)
