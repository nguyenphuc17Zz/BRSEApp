import datetime
import json
import re
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import WorkItem, WorkItemEvidence

class TodoExtractor:
    """Extracts TODO action items, assignees, and normalizes relative deadlines to absolute dates."""

    @classmethod
    def resolve_relative_deadline(cls, deadline_str: str, base_date: Optional[datetime.date] = None) -> Optional[str]:
        """Resolves relative Japanese date phrases to absolute ISO date strings (YYYY-MM-DD)."""
        if not deadline_str:
            return None

        today = base_date or datetime.date.today()
        d_lower = deadline_str.strip().lower()

        if "明日" in d_lower:
            return (today + datetime.timedelta(days=1)).isoformat()
        elif "明後日" in d_lower:
            return (today + datetime.timedelta(days=2)).isoformat()
        elif "今週中" in d_lower or "今週金曜" in d_lower:
            days_ahead = 4 - today.weekday() # Friday
            if days_ahead <= 0:
                days_ahead += 7
            return (today + datetime.timedelta(days=days_ahead)).isoformat()
        elif "来週金曜" in d_lower:
            days_ahead = (4 - today.weekday()) + 7
            return (today + datetime.timedelta(days=days_ahead)).isoformat()
        elif "月末" in d_lower:
            # End of current month
            next_month = today.replace(day=28) + datetime.timedelta(days=4)
            return (next_month - datetime.timedelta(days=next_month.day)).isoformat()

        # Regex match MM/DD or YYYY/MM/DD
        match_md = re.search(r"(\d{1,2})月(\d{1,2})日", deadline_str)
        if match_md:
            m = int(match_md.group(1))
            d = int(match_md.group(2))
            return f"{today.year}-{m:02d}-{d:02d}"

        match_slash = re.search(r"(\d{1,2})/(\d{1,2})", deadline_str)
        if match_slash:
            m = int(match_slash.group(1))
            d = int(match_slash.group(2))
            return f"{today.year}-{m:02d}-{d:02d}"

        return deadline_str

    @classmethod
    async def extract_todos(
        cls,
        db: AsyncSession,
        project_id: str,
        source_text: str,
        source_type: str,
        source_id: str,
        author: Optional[str] = None,
        timestamp: Optional[str] = None,
        provider_name: str = "gemini",
        model: Optional[str] = None
    ) -> List[WorkItem]:
        """Extracts actionable tasks, assignees, and deadlines."""
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        prompt = f"""Extract action items, tasks, assignees, and deadlines from this technical message.
If no assignee is specified, use "Unassigned".
If a deadline is mentioned (e.g. 明日まで, 9/10), extract it.

Text:
"{source_text}"

Return JSON:
{{
  "todos": [
    {{
      "task": "Specific task title",
      "assignee": "Name or Unassigned",
      "deadline_raw": "Original date text if mentioned",
      "priority": "HIGH / MEDIUM / LOW"
    }}
  ]
}}"""

        extracted = []
        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="Extract explicit actionable TODOs accurately without guessing assignees.",
                model=model,
                temperature=0.1,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            extracted = parsed.get("todos", [])
        except Exception as e:
            logger.warning(f"TODO extraction error: {e}")

        # Fallback simple heuristic
        if not extracted and any(k in source_text for k in ["お願いします", "対応", "確認して", "実装して", "更新して"]):
            extracted = [{
                "task": source_text[:60],
                "assignee": "Unassigned",
                "deadline_raw": None,
                "priority": "MEDIUM"
            }]

        saved = []
        for t in extracted:
            resolved_deadline = cls.resolve_relative_deadline(t.get("deadline_raw"))
            work_item = WorkItem(
                project_id=project_id,
                item_type="TODO",
                title=t.get("task", "Action Item"),
                description=t.get("task", ""),
                assignee=t.get("assignee", "Unassigned"),
                deadline_date=resolved_deadline,
                priority=t.get("priority", "MEDIUM"),
                status="PROPOSED",
                confidence=0.88
            )
            db.add(work_item)
            await db.flush()

            evidence = WorkItemEvidence(
                work_item_id=work_item.id,
                source_type=source_type,
                source_id=source_id,
                quote_text=source_text,
                author=author,
                timestamp=timestamp,
                confidence=work_item.confidence,
                confirmation_status="PROPOSED"
            )
            db.add(evidence)
            saved.append(work_item)

        await db.commit()
        return saved
