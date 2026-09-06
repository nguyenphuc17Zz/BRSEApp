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

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="vi")
    default_style: Mapped[str] = mapped_column(String(50), default="business")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    instructions: Mapped[List["ProjectInstruction"]] = relationship("ProjectInstruction", back_populates="project", cascade="all, delete-orphan")
    glossary_terms: Mapped[List["GlossaryTerm"]] = relationship("GlossaryTerm", back_populates="project")
    translation_memories: Mapped[List["TranslationMemory"]] = relationship("TranslationMemory", back_populates="project")
    results: Mapped[List["TranslationResult"]] = relationship("TranslationResult", back_populates="project")
    corrections: Mapped[List["TranslationCorrection"]] = relationship("TranslationCorrection", back_populates="project")

class ProjectInstruction(Base):
    __tablename__ = "project_instructions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general") # general, terminology, formatting, tone
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="instructions")

class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(20), default="project", index=True) # global, company, client, project, personal
    source_term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_term: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="vi")
    definition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), default="IT")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="glossary_terms")

class TranslationMemory(Base):
    __tablename__ = "translation_memory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="vi")
    style: Mapped[Optional[str]] = mapped_column(String(50), default="business")
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quality_signal: Mapped[float] = mapped_column(Float, default=1.0)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_vector: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # JSON float array of embeddings
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="translation_memories")

class TranslationSession(Base):
    __tablename__ = "translation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="New Translation Session")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    results: Mapped[List["TranslationResult"]] = relationship("TranslationResult", back_populates="session", cascade="all, delete-orphan")

class TranslationResult(Base):
    __tablename__ = "translation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("translation_sessions.id", ondelete="CASCADE"), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_language: Mapped[str] = mapped_column(String(10), default="ja")
    target_language: Mapped[str] = mapped_column(String(10), default="vi")
    style: Mapped[str] = mapped_column(String(50), default="auto")
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    selected_translation: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_translations_json: Mapped[str] = mapped_column(Text, default="[]") # JSON list of {text, style, confidence, reason}
    ambiguity_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    ambiguity_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    qa_warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    used_glossary_json: Mapped[str] = mapped_column(Text, default="[]")
    used_memory_json: Mapped[str] = mapped_column(Text, default="[]")
    user_correction_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)

    session: Mapped[Optional["TranslationSession"]] = relationship("TranslationSession", back_populates="results")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="results")

class TranslationCorrection(Base):
    __tablename__ = "translation_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    original_translation: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_translation: Mapped[str] = mapped_column(Text, nullable=False)
    language_pair: Mapped[str] = mapped_column(String(20), default="ja-vi")
    context_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    apply_scope: Mapped[str] = mapped_column(String(20), default="project") # project, global
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="corrections")

class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False) # e.g. "Default IT Comtor", "Executive Reporting"
    target_language: Mapped[str] = mapped_column(String(10), default="vi")
    register: Mapped[str] = mapped_column(String(50), default="business") # business, polite, very_polite, natural, technical, casual
    formality_rules: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    technical_handling: Mapped[str] = mapped_column(String(255), default="Keep API and parameter names in original English/alphabet")
    sentence_length: Mapped[str] = mapped_column(String(50), default="concise")
    custom_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class ProviderConfig(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True) # gemini, groq, ollama
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_model: Mapped[str] = mapped_column(String(100), nullable=False)
    available_models_json: Mapped[str] = mapped_column(Text, default="[]")
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=False)
    health_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)

class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # simple, technical, ambiguous, reply, explain, sensitive
    preferred_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    fallback_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    preferred_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    max_input_chars: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class ConversationContext(Base):
    __tablename__ = "conversation_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    sender: Mapped[str] = mapped_column(String(50), default="user") # user, partner, assistant, system
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
