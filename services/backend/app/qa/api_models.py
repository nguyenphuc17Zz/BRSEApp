"""QA Phase 3 models: API catalog, environments, test configs, assertions, flows."""
import datetime
import uuid
from typing import Optional, List
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.core.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class APIEndpoint(Base):
    """One API operation from an OpenAPI spec or manual entry, per project."""
    __tablename__ = "qa_api_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auth_type: Mapped[str] = mapped_column(String(30), nullable=False, default="none")
    # none | bearer | api_key | basic
    parameters_json: Mapped[str] = mapped_column(Text, default="[]")
    request_body_json: Mapped[str] = mapped_column(Text, default="{}")
    responses_json: Mapped[str] = mapped_column(Text, default="{}")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    requirement_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("work_items.id", ondelete="SET NULL"), nullable=True, index=True)
    spec_source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # openapi | manual | doc
    spec_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, index=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    test_configs: Mapped[List["APITestConfig"]] = relationship("APITestConfig", back_populates="endpoint")


class APIEnvironment(Base):
    """Named environment (DEV/STG/UAT/PROD) with base URL, public vars, encrypted secrets."""
    __tablename__ = "qa_api_environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    variables_json: Mapped[str] = mapped_column(Text, default="{}")
    secrets_json: Mapped[str] = mapped_column(Text, default="{}")  # Fernet-encrypted values
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class APITestConfig(Base):
    """Sidecar 1-1 automation config for a TestCase that is an API test. TestCase itself untouched."""
    __tablename__ = "qa_api_test_configs"
    __test__ = False

    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), primary_key=True)
    endpoint_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("qa_api_endpoints.id", ondelete="SET NULL"), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False, default="GET")
    url_template: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    query_json: Mapped[str] = mapped_column(Text, default="{}")
    path_params_json: Mapped[str] = mapped_column(Text, default="{}")
    body_text: Mapped[str] = mapped_column(Text, default="")
    auth_ref_json: Mapped[str] = mapped_column(Text, default="{}")
    # {"type": "none|bearer|api_key|basic", "secret_key": "AUTH_TOKEN"|..., "header": "X-Key", "username": ...}
    expected_status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    retry_network: Mapped[bool] = mapped_column(Boolean, default=False)
    spec_version: Mapped[str] = mapped_column(String(50), nullable=False, default="v1")
    outdated_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    is_setup: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cleanup: Mapped[bool] = mapped_column(Boolean, default=False)
    extract_map_json: Mapped[str] = mapped_column(Text, default="{}")
    # {"user_id": "data.id"} — saved into flow/run variables after execution
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    endpoint: Mapped[Optional["APIEndpoint"]] = relationship("APIEndpoint", back_populates="test_configs")
    assertions: Mapped[List["APIAssertion"]] = relationship(
        "APIAssertion",
        primaryjoin="APITestConfig.test_case_id == APIAssertion.test_case_id",
        foreign_keys="[APIAssertion.test_case_id]",
        viewonly=True)


class APIAssertion(Base):
    """One check on an API response. AI-generated rows stay DRAFT until human approves."""
    __tablename__ = "qa_api_assertions"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("qa_test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(20), nullable=False, default="status")
    # status | json | header | time | empty
    target: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # status code implied; json path (data.status); header name; empty path
    operator: Mapped[str] = mapped_column(String(20), nullable=False, default="eq")
    # eq | ne | exists | not_exists | type | contains | gt | gte | lt | lte | empty | not_empty
    expected_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    # DRAFT | APPROVED | REJECTED
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)


class APITestFlow(Base):
    """Minimal ordered flow: setup → steps (with response extracts) → cleanup."""
    __tablename__ = "qa_api_flows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    step_case_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    setup_case_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    cleanup_case_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
