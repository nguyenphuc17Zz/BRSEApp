"""QA Workspace Phase 2 models: test runs, executions, evidence, history, reports."""
import datetime
import uuid
from typing import Optional, List
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class TestRun(Base):
    """A test campaign (build / UAT / feature test). References Phase 1 test cases, never duplicates them."""
    __tablename__ = "qa_test_runs"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    run_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_build: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    scope_json: Mapped[str] = mapped_column(Text, default="{}")
    start_date: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    end_date: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tester: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | READY | IN_PROGRESS | COMPLETED | CANCELLED
    run_type: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL", index=True)
    # MANUAL | API | WEB_UI | REGRESSION | MIXED (Phase 5 adds REGRESSION)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    executions: Mapped[List["TestExecution"]] = relationship("TestExecution", back_populates="test_run", cascade="all, delete-orphan")


class TestExecution(Base):
    """One test case execution inside a run. Retest = new row with attempt_no+1, old row kept."""
    __tablename__ = "qa_test_executions"
    __test__ = False  # Prevent pytest from collecting this SQLAlchemy model as a test class

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    test_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    acceptance_criterion_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("acceptance_criteria.id", ondelete="SET NULL"), nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prev_execution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_test_executions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="NOT_RUN", index=True)
    # NOT_RUN | RUNNING | PASS | FAIL | BLOCKED | SKIPPED
    actual_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fail_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tester: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    executed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    bug_work_item_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    case_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")  # tc_code/title/expected at add-time
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    test_run: Mapped["TestRun"] = relationship("TestRun", back_populates="executions")
    evidence_items: Mapped[List["TestEvidence"]] = relationship("TestEvidence", back_populates="execution", cascade="all, delete-orphan")
    history: Mapped[List["TestExecutionHistory"]] = relationship("TestExecutionHistory", back_populates="execution", cascade="all, delete-orphan")


class TestEvidence(Base):
    """Evidence attached to a test execution. Files live on disk (data/qa-evidence/), DB keeps path+metadata."""
    __tablename__ = "qa_test_evidence"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    bug_work_item_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False, default="note", index=True)
    # screenshot | note | log | api_request | api_response | console_error | db_result | file | url
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)

    execution: Mapped["TestExecution"] = relationship("TestExecution", back_populates="evidence_items")


class TestExecutionHistory(Base):
    """Audit trail: who changed what and when (status, actual result, evidence, bug, retest)."""
    __tablename__ = "qa_execution_history"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    execution_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    # status | actual_result | evidence | bug | retest | run
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)

    execution: Mapped["TestExecution"] = relationship("TestExecution", back_populates="history")


class QAReport(Base):
    """Persisted QA report (summary / completion / daily) with JA+VI markdown and metrics snapshot."""
    __tablename__ = "qa_reports"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_test_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False, default="summary", index=True)
    # summary | completion | daily
    scope_build: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    markdown_vi: Mapped[str] = mapped_column(Text, nullable=False, default="")
    markdown_ja: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | APPROVED
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
