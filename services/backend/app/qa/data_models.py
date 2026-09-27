"""QA Phase 6 models: data sources, QA jobs, mappings, quality rules, snapshots, differences."""
import datetime
import uuid
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class DataSource(Base):
    """Named data source: uploaded file (csv/excel/json), API result snapshot, or manual table."""
    __tablename__ = "qa_data_sources"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # file_csv | file_excel | file_json | api_result | snapshot | manual_table
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    # {file_path, sheet, encoding, delimiter, json_path, ...} — never credentials
    schema_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)


class DataQaJob(Base):
    """One validation job: source vs destination + rules + mapping."""
    __tablename__ = "qa_data_jobs"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    job_code: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_data_sources.id", ondelete="SET NULL"), nullable=True)
    dest_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_data_sources.id", ondelete="SET NULL"), nullable=True)
    requirement_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    build: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | READY | RUNNING | COMPLETED | FAILED
    key_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    # business key after mapping, e.g. ["order_no", "detail_no"]
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    # {possible_dup_fields: [...], normalize: {...}, row_cap: 100000}
    sync_tolerance_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class FieldMapping(Base):
    """Source field -> destination field + transform, or ignored. DRAFT until reviewed."""
    __tablename__ = "qa_field_mappings"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_data_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_field: Mapped[str] = mapped_column(String(255), nullable=False)
    dest_field: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    transform_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # {"op": "date_format", "from": "%Y%m%d", "to": "%Y/%m/%d"} | {"op": "trim"} | ...
    ignored: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | APPROVED
    ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class DataQualityRule(Base):
    """Validation rule linked to requirement/AC/decision. AI output stays DRAFT."""
    __tablename__ = "qa_data_rules"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_data_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    test_case_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    requirement_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # required | unique | range | format | ref_integrity | cross_field | calculation
    # | consistency | mapping | custom_sql
    definition_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | APPROVED | REJECTED
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="user")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)


class DataSnapshot(Base):
    """Before/after snapshot: file on disk + metadata/hash in DB."""
    __tablename__ = "qa_data_snapshots"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_data_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(20), nullable=False)
    # source | dest
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)


class DataDifference(Base):
    """One detected difference with evidence. Rows capped per job; rest aggregated."""
    __tablename__ = "qa_data_differences"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_data_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_test_executions.id", ondelete="SET NULL"), nullable=True, index=True)
    diff_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # missing | extra | mismatch | rule_violation | duplicate | encoding
    biz_key: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    field: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    expected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    severity_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rule_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_data_rules.id", ondelete="SET NULL"), nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", index=True)
    # OPEN | BUG_FILED | RESOLVED
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
