"""QA Workspace Phase 1 models: findings, open questions, acceptance criteria, test cases/steps, coverage."""
import datetime
import uuid
from typing import Optional, List
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class QAFinding(Base):
    """A single QA issue detected during requirement review. Evidence-first: every finding must carry evidence_quote."""
    __tablename__ = "qa_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    finding_type: Mapped[str] = mapped_column(String(40), nullable=False, default="Ambiguous", index=True)
    # Ambiguous | MissingInformation | MissingValidation | MissingExpectedResult | MissingErrorHandling
    # | MissingPermission | MissingBoundary | Conflict | NonTestable
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.80)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="requirement")
    evidence_source_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    knowledge_class: Mapped[str] = mapped_column(String(20), nullable=False, default="Confirmed")
    # Confirmed | Inferred | AISuggested
    suggested_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    # OPEN | RESOLVED | IGNORED
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class QAOpenQuestion(Base):
    """Clarification question for the client. Standalone table (human decision) with JA keigo + VI explanation."""
    __tablename__ = "qa_open_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    finding_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_findings.id", ondelete="SET NULL"), nullable=True, index=True)
    question_vi: Mapped[str] = mapped_column(Text, nullable=False)
    question_ja: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_if_unanswered: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | APPROVED | ANSWERED | REJECTED
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class AcceptanceCriterion(Base):
    """Given/When/Then acceptance criterion linked to a requirement. AI output defaults to DRAFT."""
    __tablename__ = "acceptance_criteria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    ac_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    given_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    when_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    then_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_class: Mapped[str] = mapped_column(String(20), nullable=False, default="Confirmed")
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | APPROVED | REJECTED
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    test_cases: Mapped[List["TestCase"]] = relationship("TestCase", back_populates="acceptance_criterion", cascade="all, delete-orphan")


class TestCase(Base):
    """QA test case with structured steps. Linked to requirement and optionally one acceptance criterion."""
    __tablename__ = "qa_test_cases"
    __test__ = False  # Prevent pytest from collecting this SQLAlchemy model as a test class

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    tc_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    case_type: Mapped[str] = mapped_column(String(30), nullable=False, default="Happy", index=True)
    # Happy | Negative | Validation | Boundary | Permission | DataIntegrity | ErrorHandling | StateTransition | RegressionCandidate
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM", index=True)
    preconditions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    acceptance_criterion_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("acceptance_criteria.id", ondelete="SET NULL"), nullable=True, index=True)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_class: Mapped[str] = mapped_column(String(20), nullable=False, default="Confirmed")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="AI")
    # AI | Manual | MeetingDecision
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.80)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | REVIEWED | APPROVED | REJECTED
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    acceptance_criterion: Mapped[Optional["AcceptanceCriterion"]] = relationship("AcceptanceCriterion", back_populates="test_cases")
    steps: Mapped[List["TestStep"]] = relationship("TestStep", back_populates="test_case", cascade="all, delete-orphan", order_by="TestStep.step_order")


class TestStep(Base):
    """Structured step of a test case: action + expected outcome."""
    __tablename__ = "qa_test_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str] = mapped_column(Text, nullable=False, default="")

    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="steps")


class RequirementCoverage(Base):
    """Materialized coverage snapshot per requirement, refreshed after every QA mutation."""
    __tablename__ = "requirement_coverage"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    has_review: Mapped[bool] = mapped_column(Boolean, default=False)
    findings_open: Mapped[int] = mapped_column(Integer, default=0)
    questions_unanswered: Mapped[int] = mapped_column(Integer, default=0)
    ac_total: Mapped[int] = mapped_column(Integer, default=0)
    ac_approved: Mapped[int] = mapped_column(Integer, default=0)
    tc_total: Mapped[int] = mapped_column(Integer, default=0)
    tc_approved: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="NotReviewed", index=True)
    # NotReviewed | NotCovered | PartiallyCovered | Covered | BlockedByClarification
    # --- Phase 2 execution coverage ---
    exec_total: Mapped[int] = mapped_column(Integer, default=0)
    exec_executed: Mapped[int] = mapped_column(Integer, default=0)
    exec_passed: Mapped[int] = mapped_column(Integer, default=0)
    exec_failed: Mapped[int] = mapped_column(Integer, default=0)
    exec_blocked: Mapped[int] = mapped_column(Integer, default=0)
    exec_status: Mapped[str] = mapped_column(String(20), nullable=False, default="Designed")
    # Designed | NotExecuted | Passed | Failed | Blocked
    last_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_build: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
