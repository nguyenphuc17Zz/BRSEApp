"""QA Phase 4 models: UI automation scripts (versioned), element mappings, page knowledge."""
import datetime
import uuid
from typing import Optional, List
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class UIAutomationScript(Base):
    """Sidecar 1-1 automation for a TestCase that is a WEB_UI test. TestCase itself untouched."""
    __tablename__ = "qa_ui_scripts"
    __test__ = False

    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), primary_key=True)
    flow_json: Mapped[str] = mapped_column(Text, default="[]")
    # visual steps: [{order, action, target, value, assertion}]
    script_text: Mapped[str] = mapped_column(Text, default="")
    script_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_GENERATED", index=True)
    # NOT_GENERATED | GENERATED | REVIEW_REQUIRED | APPROVED | NEEDS_UPDATE | DISABLED
    # (RUNNING/PASS/FAIL live on TestExecution, never here)
    playwright_version: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    is_smoke: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_preferred_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flaky_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    update_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    history: Mapped[List["UIAutomationScriptHistory"]] = relationship(
        "UIAutomationScriptHistory", back_populates="script",
        cascade="all, delete-orphan", order_by="UIAutomationScriptHistory.version")


class UIAutomationScriptHistory(Base):
    """Version history: regenerate never overwrites silently."""
    __tablename__ = "qa_ui_script_history"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_ui_scripts.test_case_id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    script_text: Mapped[str] = mapped_column(Text, default="")
    flow_json: Mapped[str] = mapped_column(Text, default="[]")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    script: Mapped["UIAutomationScript"] = relationship("UIAutomationScript", back_populates="history")


class UIElementMapping(Base):
    """Reusable locator: one element, many test cases. AI uses only ACTIVE rows."""
    __tablename__ = "qa_ui_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    element_name: Mapped[str] = mapped_column(String(150), nullable=False)
    locator_json: Mapped[str] = mapped_column(Text, default="{}")
    # {"strategy": "role|label|placeholder|text|testid|css", "value": ..., "options": {...}}
    fallback_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    # ACTIVE | NEEDS_REVIEW
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class UIPageKnowledge(Base):
    """Lightweight page/screen knowledge: URL, actions, notes. No full POM."""
    __tablename__ = "qa_ui_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_name: Mapped[str] = mapped_column(String(150), nullable=False)
    url_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    common_actions_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
