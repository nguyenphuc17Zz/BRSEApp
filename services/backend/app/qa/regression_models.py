"""QA Phase 5 models: change records, requirement versions, regression plans."""
import datetime
import uuid
from typing import Optional, List
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class ChangeRecord(Base):
    """One tracked change (requirement update, spec, decision, bug fix...). User-created, AI-assisted."""
    __tablename__ = "qa_change_records"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    change_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # requirement_update | spec | decision | meeting | ac_change | api_spec | ui_change
    # | bug_fix | change_request | document
    requirement_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True)
    bug_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    old_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    new_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    business_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    categories_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", index=True)
    risk_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | ANALYZED | SUPERSEDED
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)

    plan_links: Mapped[List["RegressionPlanChange"]] = relationship(
        "RegressionPlanChange", back_populates="change", cascade="all, delete-orphan")


class RequirementVersion(Base):
    """Version history of a requirement (v1 -> v2 -> v3)."""
    __tablename__ = "qa_requirement_versions"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ac_snapshot_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    # change:<change_id> | manual
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)


class RegressionPlan(Base):
    """Human-approved regression set. DRAFT -> REVIEWED -> APPROVED. AI never auto-runs."""
    __tablename__ = "qa_regression_plans"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    release_tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | REVIEWED | APPROVED
    time_budget_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    test_run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_test_runs.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    changes: Mapped[List["RegressionPlanChange"]] = relationship(
        "RegressionPlanChange", back_populates="plan", cascade="all, delete-orphan")
    items: Mapped[List["RegressionPlanItem"]] = relationship(
        "RegressionPlanItem", back_populates="plan", cascade="all, delete-orphan")


class RegressionPlanChange(Base):
    """Links plans to changes (release change sets, combined impact)."""
    __tablename__ = "qa_regression_plan_changes"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_regression_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    change_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_change_records.id", ondelete="CASCADE"), nullable=False, index=True)

    plan: Mapped["RegressionPlan"] = relationship("RegressionPlan", back_populates="changes")
    change: Mapped["ChangeRecord"] = relationship("ChangeRecord", back_populates="plan_links")


class RegressionPlanItem(Base):
    """One test in a plan with tier, reason, relationship path, risk, confidence."""
    __tablename__ = "qa_regression_plan_items"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_regression_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="RECOMMENDED", index=True)
    # MUST_RUN | RECOMMENDED | OPTIONAL | EXCLUDED
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    relationship_path: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    risk: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    impact_confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")
    # High | Medium | Low — confidence in the RELATIONSHIP, never release safety
    priority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=999)
    added_by: Mapped[str] = mapped_column(String(20), nullable=False, default="ai")
    # ai | user
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    # PENDING | IN_RUN | DONE | SKIPPED
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    plan: Mapped["RegressionPlan"] = relationship("RegressionPlan", back_populates="items")
