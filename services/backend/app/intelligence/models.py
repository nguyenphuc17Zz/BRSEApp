import datetime
import uuid
from typing import Optional, List
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON, func
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class WorkItem(Base):
    """Unified work item model across Requirements, Bugs, Decisions, TODOs, Risks, Open Questions."""
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # REQUIREMENT, BUG, QUESTION, DECISION, TODO, RISK, DEADLINE, DEPENDENCY, OPEN_QUESTION, MEETING_ITEM
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, default="{}") # structured fields (Actor, Action, Condition, Env, Expected vs Actual, etc.)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED", index=True)
    # PROPOSED, CONFIRMED, IN_PROGRESS, BLOCKED, DONE, REJECTED, SUPERSEDED, NEEDS_CONFIRMATION, CONFLICT
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM", index=True) # CRITICAL, HIGH, MEDIUM, LOW
    assignee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    deadline_date: Mapped[Optional[str]] = mapped_column(String(30), nullable=True) # Normalized date string e.g. 2026-09-10
    confidence: Mapped[float] = mapped_column(Float, default=0.85)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    evidence_items: Mapped[List["WorkItemEvidence"]] = relationship("WorkItemEvidence", back_populates="work_item", cascade="all, delete-orphan")

class WorkItemEvidence(Base):
    """Preserves concrete proof and source quotes for every AI-extracted work item."""
    __tablename__ = "work_item_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    work_item_id: Mapped[str] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False) # slack, line, docx, pdf, gdoc, gsheet, meeting
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.90)
    confirmation_status: Mapped[str] = mapped_column(String(30), default="PROPOSED") # CONFIRMED, PROPOSED, ASSUMED, UNCLEAR, CONTRADICTED
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    work_item: Mapped["WorkItem"] = relationship("WorkItem", back_populates="evidence_items")

class ProjectRelationship(Base):
    """Lightweight knowledge graph relationships connecting project entities."""
    __tablename__ = "project_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False) # requirement, bug, decision, todo, document
    source_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False) # depends_on, contradicted_by, changed_by, related_to, mentioned_in, implemented_by
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class MeetingRecord(Base):
    """Stores meeting transcripts, business-ready minutes, action items, and attendees."""
    __tablename__ = "meeting_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    meeting_date: Mapped[str] = mapped_column(String(30), nullable=False)
    participants_json: Mapped[str] = mapped_column(Text, default="[]")
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    decisions_json: Mapped[str] = mapped_column(Text, default="[]")
    action_items_json: Mapped[str] = mapped_column(Text, default="[]")
    open_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class AutomationRule(Base):
    """User-configurable workflow automation policies."""
    __tablename__ = "automation_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    event_trigger: Mapped[str] = mapped_column(String(50), nullable=False) # message_received, requirement_extracted, deadline_detected, bug_detected
    condition_json: Mapped[str] = mapped_column(Text, default="{}")
    action_type: Mapped[str] = mapped_column(String(50), nullable=False) # translate_and_draft_reply, create_inbox_item, flag_conflict
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class AutomationRunLog(Base):
    """Audit trail of all automation triggers and proposals (never silent external actions)."""
    __tablename__ = "automation_run_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    rule_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(100), nullable=False)
    ai_decision: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class ProjectDocumentChunk(Base):
    """Document chunks indexed for token-safe Project Document RAG retrieval."""
    __tablename__ = "project_document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class ProjectStakeholder(Base):
    """Project stakeholders, speakers, and communicators for Smart Message Analyzer & Meeting Intelligence."""
    __tablename__ = "project_stakeholders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(100), default="Client PM") # Client PM, Product Owner, Tech Lead, BrSE, QA Lead, Dev, Stakeholder
    organization: Mapped[str] = mapped_column(String(100), default="Khách hàng") # Khách hàng (Client), Nội bộ (Offshore), Đối tác (Partner)
    platform: Mapped[Optional[str]] = mapped_column(String(50), default="all") # slack, line, email, meeting, all
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class LineCapturedMessage(Base):
    """Captured LINE messages (via Webhook or Simulator) with RAG grounding, smart replies, and sync metadata."""
    __tablename__ = "line_captured_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(128), default="line-group-default")
    message_id: Mapped[str] = mapped_column(String(128), index=True)
    sender: Mapped[str] = mapped_column(String(150), default="Client (LINE)")
    sender_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("project_stakeholders.id", ondelete="SET NULL"), nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    reply_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detected_intent: Mapped[str] = mapped_column(String(64), default="NORMAL")
    commitment_warning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_replies: Mapped[list] = mapped_column(JSON, default=list)
    rag_sources: Mapped[list] = mapped_column(JSON, default=list)
    sync_result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

