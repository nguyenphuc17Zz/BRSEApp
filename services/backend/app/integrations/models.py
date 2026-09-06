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

class IntegrationAccount(Base):
    """Stores OAuth connection tokens (AES-256 encrypted) and status for Google & Slack."""
    __tablename__ = "integration_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True) # google, slack
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    workspace_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scopes_json: Mapped[str] = mapped_column(Text, default="[]")
    token_expiry: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    slack_mappings: Mapped[List["SlackChannelMapping"]] = relationship("SlackChannelMapping", back_populates="account", cascade="all, delete-orphan")
    google_mappings: Mapped[List["GoogleFolderMapping"]] = relationship("GoogleFolderMapping", back_populates="account", cascade="all, delete-orphan")

class SlackChannelMapping(Base):
    """Maps a Slack channel to an active Project Workspace with priority threshold."""
    __tablename__ = "slack_channel_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("integration_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    channel_name: Mapped[str] = mapped_column(String(100), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    auto_translate: Mapped[bool] = mapped_column(Boolean, default=False)
    min_priority_score: Mapped[int] = mapped_column(Integer, default=60) # 0-100 threshold
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    account: Mapped["IntegrationAccount"] = relationship("IntegrationAccount", back_populates="slack_mappings")

class GoogleFolderMapping(Base):
    """Maps a Google Drive folder to an active Project Workspace."""
    __tablename__ = "google_folder_mappings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("integration_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    folder_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    folder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    account: Mapped["IntegrationAccount"] = relationship("IntegrationAccount", back_populates="google_mappings")

class IntegrationCache(Base):
    """Cache for Slack message threads and Google Docs/Sheets content (7-day default TTL)."""
    __tablename__ = "integration_caches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # slack_thread, google_doc, google_sheet, google_slide
    source_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, index=True)

class DesktopProfile(Base):
    """Configuration mapping active application processes to translation modes and projects."""
    __tablename__ = "desktop_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    process_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True) # e.g. slack.exe, winword.exe
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(30), default="generic") # conversation, document, table, presentation, web, generic
    default_project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

class IntegrationAuditLog(Base):
    """Audit log recording technical metadata for all integration actions."""
    __tablename__ = "integration_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    integration: Mapped[str] = mapped_column(String(30), nullable=False, index=True) # google, slack, desktop
    operation: Mapped[str] = mapped_column(String(60), nullable=False, index=True) # translate_doc, translate_thread, quick_translate, etc.
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), default="gemini")
    model: Mapped[str] = mapped_column(String(100), default="gemini-3.5-flash-lite")
    status: Mapped[str] = mapped_column(String(30), default="success")
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
