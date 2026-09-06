import datetime
import uuid
from typing import Optional, List
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class DocumentFile(Base):
    __tablename__ = "document_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True) # docx, xlsx, pptx, pdf
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    original_path: Mapped[str] = mapped_column(String(500), nullable=False)
    detected_language: Mapped[str] = mapped_column(String(10), default="ja")
    unit_count: Mapped[int] = mapped_column(Integer, default=1) # pages, sheets, slides, or sections count
    unit_label: Mapped[str] = mapped_column(String(20), default="pages") # pages, sheets, slides, sections
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    jobs: Mapped[List["DocumentJob"]] = relationship("DocumentJob", back_populates="document", cascade="all, delete-orphan")

class DocumentJob(Base):
    __tablename__ = "document_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_files.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    # queued, analyzing, segmenting, translating, qa, rendering, completed, partially_completed, failed, cancelled, paused
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="vi")
    provider: Mapped[str] = mapped_column(String(50), default="gemini")
    model: Mapped[str] = mapped_column(String(100), default="gemini-3.5-flash-lite")
    style: Mapped[str] = mapped_column(String(50), default="business")
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    total_segments: Mapped[int] = mapped_column(Integer, default=0)
    completed_segments: Mapped[int] = mapped_column(Integer, default=0)
    failed_segments: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    current_stage: Mapped[str] = mapped_column(String(255), default="Initialized")
    output_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    output_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    document: Mapped["DocumentFile"] = relationship("DocumentFile", back_populates="jobs")
    segments: Mapped[List["DocumentSegment"]] = relationship("DocumentSegment", back_populates="job", cascade="all, delete-orphan")
    issues: Mapped[List["DocumentIssue"]] = relationship("DocumentIssue", back_populates="job", cascade="all, delete-orphan")

class DocumentSegment(Base):
    __tablename__ = "document_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    location_json: Mapped[str] = mapped_column(Text, nullable=False) # e.g. {"sheet": "Requirements", "cell": "A1"}
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    protected_tokens_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True) # pending, translating, translated, qa_warning, user_edited, failed
    qa_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    context_hint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    job: Mapped["DocumentJob"] = relationship("DocumentJob", back_populates="segments")

class DocumentIssue(Base):
    __tablename__ = "document_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING") # INFO, WARNING, ERROR, CRITICAL
    category: Mapped[str] = mapped_column(String(50), nullable=False) # formula_preserved, token_mismatch, number_mismatch, overflow
    location_text: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    job: Mapped["DocumentJob"] = relationship("DocumentJob", back_populates="issues")
