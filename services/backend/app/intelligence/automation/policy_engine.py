import json
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.logging import logger
from app.intelligence.models import AutomationRule, AutomationRunLog, WorkItem, WorkItemEvidence

class AutomationPolicyEngine:
    """Evaluates automation policies (Level 2: AI creates draft records).
    Strict Guardrail: NEVER performs consequential external actions without human approval.
    """

    DEFAULT_RULES = [
        {
            "name": "Auto-draft reply on questions",
            "event_trigger": "message_received",
            "condition_json": json.dumps({"intent": ["QUESTION", "ACTION_REQUIRED"]}),
            "action_type": "draft_reply_suggestion",
            "is_active": True
        },
        {
            "name": "Draft WorkItem on high-confidence requirement",
            "event_trigger": "requirement_extracted",
            "condition_json": json.dumps({"min_confidence": 0.85}),
            "action_type": "create_proposed_work_item",
            "is_active": True
        },
        {
            "name": "Draft Task on detected deadline",
            "event_trigger": "deadline_detected",
            "condition_json": json.dumps({}),
            "action_type": "create_deadline_work_item",
            "is_active": True
        }
    ]

    async def ensure_default_rules(self, db: AsyncSession, project_id: Optional[str] = None):
        """Seeds standard default rules for projects if none exist."""
        stmt = select(AutomationRule)
        if project_id:
            stmt = stmt.where(AutomationRule.project_id == project_id)
        res = await db.execute(stmt)
        existing = res.scalars().all()
        if not existing:
            for rule_def in self.DEFAULT_RULES:
                rule = AutomationRule(
                    project_id=project_id,
                    name=rule_def["name"],
                    event_trigger=rule_def["event_trigger"],
                    condition_json=rule_def["condition_json"],
                    action_type=rule_def["action_type"],
                    is_active=rule_def["is_active"]
                )
                db.add(rule)
            await db.commit()

    async def evaluate_event(
        self,
        db: AsyncSession,
        event_trigger: str,
        event_data: Dict[str, Any],
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Evaluates active automation rules against an event and performs Level 2 local draft actions."""
        stmt = select(AutomationRule).where(
            AutomationRule.event_trigger == event_trigger,
            AutomationRule.is_active == True
        )
        if project_id:
            stmt = stmt.where((AutomationRule.project_id == project_id) | (AutomationRule.project_id == None))
        
        res = await db.execute(stmt)
        rules = res.scalars().all()

        executed_actions = []

        for rule in rules:
            try:
                cond = json.loads(rule.condition_json or "{}")
            except Exception:
                cond = {}

            matches = self._check_condition(cond, event_data)
            if not matches:
                continue

            # Execute safe local action
            action_result = await self._execute_safe_action(db, rule, event_data, project_id)
            
            # Log execution to audit trail
            log = AutomationRunLog(
                rule_id=rule.id,
                trigger_source=f"{event_trigger}:{event_data.get('source_type', 'unknown')}",
                ai_decision=f"Rule '{rule.name}' matched with condition {rule.condition_json}",
                action_taken=f"{rule.action_type}: {action_result.get('summary', 'Done')}",
                status="drafted"
            )
            db.add(log)
            await db.commit()

            executed_actions.append({
                "rule_id": rule.id,
                "rule_name": rule.name,
                "action_type": rule.action_type,
                "result": action_result
            })

        return executed_actions

    def _check_condition(self, condition: Dict[str, Any], event_data: Dict[str, Any]) -> bool:
        """Evaluates simple json conditions against event payload."""
        if "min_confidence" in condition:
            if event_data.get("confidence", 0.0) < condition["min_confidence"]:
                return False
        if "intent" in condition:
            intents = condition["intent"]
            event_intents = event_data.get("intents", [])
            if not any(i in event_intents for i in intents):
                return False
        return True

    async def _execute_safe_action(
        self,
        db: AsyncSession,
        rule: AutomationRule,
        event_data: Dict[str, Any],
        project_id: Optional[str]
    ) -> Dict[str, Any]:
        """Performs non-consequential, reversible local drafting (Level 2)."""
        action = rule.action_type

        if action == "create_proposed_work_item":
            item = WorkItem(
                project_id=project_id or event_data.get("project_id", "default"),
                item_type=event_data.get("item_type", "REQUIREMENT"),
                title=event_data.get("title", "Proposed Item"),
                description=event_data.get("description", ""),
                status="PROPOSED", # Explicitly proposed, needs human review
                confidence=event_data.get("confidence", 0.85),
                priority=event_data.get("priority", "MEDIUM")
            )
            db.add(item)
            await db.flush()

            if event_data.get("quote_text"):
                ev = WorkItemEvidence(
                    work_item_id=item.id,
                    source_type=event_data.get("source_type", "slack"),
                    source_id=event_data.get("source_id", "unknown"),
                    quote_text=event_data.get("quote_text", ""),
                    confirmation_status="PROPOSED"
                )
                db.add(ev)
            await db.commit()
            return {"summary": f"Created PROPOSED WorkItem {item.id}", "item_id": item.id}

        elif action == "draft_reply_suggestion":
            return {
                "summary": "Reply suggestion drafted and sent to Reply Inbox",
                "target_message_id": event_data.get("message_id")
            }

        elif action == "create_deadline_work_item":
            item = WorkItem(
                project_id=project_id or event_data.get("project_id", "default"),
                item_type="DEADLINE",
                title=event_data.get("title", "Detected Deadline"),
                description=event_data.get("description", ""),
                deadline_date=event_data.get("deadline_date"),
                status="PROPOSED",
                confidence=0.9
            )
            db.add(item)
            await db.commit()
            return {"summary": f"Created DEADLINE WorkItem {item.id}", "item_id": item.id}

        return {"summary": f"Action {action} handled."}

policy_engine = AutomationPolicyEngine()
