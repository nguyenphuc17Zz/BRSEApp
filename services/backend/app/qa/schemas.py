"""Pydantic schemas for QA Workspace Phase 1."""
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------- Shared ----------
class ProviderSelection(BaseModel):
    preferred_provider: Optional[str] = None
    model: Optional[str] = None


# ---------- Findings ----------
class FindingResponse(BaseModel):
    id: str
    project_id: str
    requirement_id: str
    title: str
    description: str = ""
    finding_type: str
    severity: str
    confidence: float
    evidence_quote: str = ""
    evidence_source_type: str = ""
    evidence_source_id: str = ""
    knowledge_class: str
    suggested_action: Optional[str] = None
    status: str
    ai_generated: bool
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class FindingStatusUpdate(BaseModel):
    status: str = Field(..., description="OPEN | RESOLVED | IGNORED")


class ReviewRequest(ProviderSelection):
    force: bool = False


# ---------- Open Questions ----------
class OpenQuestionResponse(BaseModel):
    id: str
    project_id: str
    requirement_id: str
    finding_id: Optional[str] = None
    question_vi: str
    question_ja: str = ""
    reason: str = ""
    evidence_quote: str = ""
    risk_if_unanswered: Optional[str] = None
    status: str
    answer_text: Optional[str] = None
    ai_generated: bool
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class OpenQuestionUpdate(BaseModel):
    question_vi: Optional[str] = None
    question_ja: Optional[str] = None
    reason: Optional[str] = None
    risk_if_unanswered: Optional[str] = None
    status: Optional[str] = None
    answer_text: Optional[str] = None


class GenerateQuestionsRequest(ProviderSelection):
    finding_ids: Optional[List[str]] = None


# ---------- Acceptance Criteria ----------
class AcceptanceCriterionResponse(BaseModel):
    id: str
    project_id: str
    requirement_id: str
    ac_code: str = ""
    given_text: str = ""
    when_text: str = ""
    then_text: str = ""
    knowledge_class: str
    evidence_quote: str = ""
    status: str
    ai_generated: bool
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class AcceptanceCriterionUpdate(BaseModel):
    given_text: Optional[str] = None
    when_text: Optional[str] = None
    then_text: Optional[str] = None
    status: Optional[str] = None


class AcceptanceCriterionCreate(BaseModel):
    given_text: str = ""
    when_text: str = ""
    then_text: str = ""
    evidence_quote: str = ""


# ---------- Test Cases ----------
class TestStepResponse(BaseModel):
    id: str
    step_order: int
    action: str
    expected: str = ""

    class Config:
        from_attributes = True


class TestStepInput(BaseModel):
    action: str
    expected: str = ""


class TestCaseResponse(BaseModel):
    id: str
    project_id: str
    tc_code: str = ""
    title: str
    purpose: str = ""
    case_type: str
    priority: str
    preconditions: str = ""
    expected_result: str = ""
    requirement_id: str
    acceptance_criterion_id: Optional[str] = None
    evidence_quote: str = ""
    knowledge_class: str
    source: str
    ai_generated: bool
    confidence: float
    status: str
    steps: List[TestStepResponse] = []
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class TestCaseUpdate(BaseModel):
    title: Optional[str] = None
    purpose: Optional[str] = None
    case_type: Optional[str] = None
    priority: Optional[str] = None
    preconditions: Optional[str] = None
    expected_result: Optional[str] = None
    acceptance_criterion_id: Optional[str] = None
    status: Optional[str] = None
    steps: Optional[List[TestStepInput]] = None


class TestCaseCreate(BaseModel):
    title: str
    purpose: str = ""
    case_type: str = "Happy"
    priority: str = "MEDIUM"
    preconditions: str = ""
    expected_result: str = ""
    acceptance_criterion_id: Optional[str] = None
    evidence_quote: str = ""
    steps: List[TestStepInput] = []


class GenerateTestCasesRequest(ProviderSelection):
    acceptance_criterion_ids: Optional[List[str]] = None
    checklist_mode: bool = False


# ---------- Phase 2: Test Runs ----------
class TestRunCreate(BaseModel):
    name: str
    version_build: str = ""
    environment: str = ""
    scope: dict = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tester: Optional[str] = None
    notes: Optional[str] = None


class TestRunUpdate(BaseModel):
    name: Optional[str] = None
    version_build: Optional[str] = None
    environment: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tester: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class TestRunResponse(BaseModel):
    id: str
    project_id: str
    run_code: str = ""
    name: str
    version_build: str = ""
    environment: str = ""
    scope: dict = {}
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    tester: Optional[str] = None
    status: str
    run_type: str = "MANUAL"
    notes: Optional[str] = None
    progress: dict = {}
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True


class AddCasesRequest(BaseModel):
    scope: dict = {}


# ---------- Phase 2: Executions ----------
class ExecutionResultRequest(BaseModel):
    status: str
    actual_result: Optional[str] = None
    notes: Optional[str] = None
    fail_reason: Optional[str] = None
    tester: Optional[str] = None
    changed_by: Optional[str] = "user"


class ExecutionResponse(BaseModel):
    id: str
    test_run_id: str
    test_case_id: str
    tc_code: str = ""
    tc_title: str = ""
    requirement_id: str
    req_code: Optional[str] = None
    acceptance_criterion_id: Optional[str] = None
    attempt_no: int = 1
    prev_execution_id: Optional[str] = None
    status: str
    actual_result: Optional[str] = None
    notes: Optional[str] = None
    fail_reason: Optional[str] = None
    tester: Optional[str] = None
    executed_at: Optional[str] = None
    bug_work_item_id: Optional[str] = None
    bug_code: Optional[str] = None
    evidence_count: int = 0
    created_at: str = ""
    updated_at: str = ""


# ---------- Phase 2: Evidence ----------
class EvidenceCreate(BaseModel):
    evidence_type: str = "note"
    title: str = ""
    text_content: Optional[str] = None
    changed_by: Optional[str] = "user"


class EvidenceResponse(BaseModel):
    id: str
    execution_id: str
    test_case_id: str
    requirement_id: str
    bug_work_item_id: Optional[str] = None
    evidence_type: str
    title: str = ""
    text_content: Optional[str] = None
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str = ""


# ---------- Phase 2: Bugs ----------
class BugDraftResponse(BaseModel):
    title_vi: str = ""
    title_ja: str = ""
    summary_vi: str = ""
    summary_ja: str = ""
    environment: str = ""
    preconditions: str = ""
    steps: list = []
    expected_result: str = ""
    actual_result: str = ""
    reproduction_rate: str = ""
    severity_suggestion: str = "MEDIUM"
    notes_ja: str = ""
    requirement_id: str = ""
    test_case_id: str = ""
    test_run_id: str = ""
    execution_id: str = ""


class BugCreateRequest(BaseModel):
    title_vi: Optional[str] = None
    title_ja: Optional[str] = None
    summary_vi: Optional[str] = None
    summary_ja: Optional[str] = None
    environment: Optional[str] = None
    preconditions: Optional[str] = None
    steps: list = []
    expected_result: Optional[str] = None
    actual_result: Optional[str] = None
    reproduction_rate: Optional[str] = None
    severity_suggestion: str = "MEDIUM"
    notes_ja: Optional[str] = None
    status: str = "PROPOSED"
    changed_by: Optional[str] = "user"


class BugResponse(BaseModel):
    id: str
    project_id: str
    bug_code: Optional[str] = None
    title: str
    description: str = ""
    details: dict = {}
    status: str
    ux_status: str = "OPEN"
    priority: str
    assignee: Optional[str] = None
    requirement_id: Optional[str] = None
    test_case_id: Optional[str] = None
    test_run_id: Optional[str] = None
    execution_id: Optional[str] = None
    evidence: list = []
    created_at: str = ""
    updated_at: str = ""


# ---------- Phase 2: Reports ----------
class ReportGenerateRequest(BaseModel):
    report_type: str = "summary"
    preferred_provider: Optional[str] = None
    model: Optional[str] = None
    created_by: Optional[str] = "user"


class ReportResponse(BaseModel):
    id: str
    project_id: str
    test_run_id: Optional[str] = None
    report_type: str
    scope_build: str = ""
    markdown_vi: str = ""
    markdown_ja: str = ""
    metrics: dict = {}
    status: str
    ai_generated: bool
    created_at: str = ""


# ---------- Coverage ----------
class CoverageResponse(BaseModel):
    project_id: str
    requirement_id: str
    requirement_title: str = ""
    req_code: Optional[str] = None
    has_review: bool
    findings_open: int
    questions_unanswered: int
    ac_total: int
    ac_approved: int
    tc_total: int
    tc_approved: int
    status: str
    computed_at: str = ""


class QAOverviewResponse(BaseModel):
    project_id: Optional[str] = None
    total_requirements: int = 0
    reviewed_requirements: int = 0
    needs_clarification: int = 0
    open_questions: int = 0
    unapproved_ac: int = 0
    covered_requirements: int = 0
    uncovered_requirements: int = 0
    testcase_draft: int = 0
    testcase_approved: int = 0
    # --- Phase 2 additions ---
    active_runs: int = 0
    exec_pass: int = 0
    exec_fail: int = 0
    exec_blocked: int = 0
    exec_not_run: int = 0
    open_bugs: int = 0
    retest_pending: int = 0
    latest_build: Optional[str] = None
    latest_build_status: Optional[str] = None
    # --- Phase 3 additions ---
    api_tests: int = 0
    api_pass: int = 0
    api_fail: int = 0
    api_endpoints: int = 0
    api_endpoints_covered: int = 0
    api_recent_failures: list = []
    # --- Phase 5 additions ---
    changes_pending: int = 0
    regression_required: int = 0
    regression_in_progress: int = 0
    high_risk_changes: int = 0
    tests_needing_update: int = 0


# ---------- Requirement Detail aggregate ----------
class RequirementDetailResponse(BaseModel):
    id: str
    project_id: str
    req_code: Optional[str] = None
    title: str
    description: str = ""
    status: str
    priority: str
    evidence_items: list = []
    findings: List[FindingResponse] = []
    questions: List[OpenQuestionResponse] = []
    acceptance_criteria: List[AcceptanceCriterionResponse] = []
    test_cases: List[TestCaseResponse] = []
    coverage: Optional[CoverageResponse] = None
    exec_summary: Optional[dict] = None
    related_bugs: List[dict] = []
    case_history: List[dict] = []

# ---------- Phase 3: API Testing ----------
class APIEndpointCreate(BaseModel):
    method: str
    path: str
    name: str = ""
    description: str = ""
    auth_type: str = "none"
    parameters: list = []
    request_body: dict = {}
    responses: dict = {}
    tags: list = []
    requirement_id: Optional[str] = None
    spec_source: str = "manual"


class APIEndpointResponse(BaseModel):
    id: str
    project_id: str
    method: str
    path: str
    name: str = ""
    description: str = ""
    auth_type: str = "none"
    parameters: list = []
    request_body: dict = {}
    responses: dict = {}
    tags: list = []
    requirement_id: Optional[str] = None
    req_code: Optional[str] = None
    spec_source: str = "manual"
    spec_version: str = "v1"
    test_case_count: int = 0
    last_result: Optional[str] = None
    last_build: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class APIEnvironmentCreate(BaseModel):
    name: str
    base_url: str = ""
    variables: dict = {}
    is_default: bool = False


class APIEnvironmentResponse(BaseModel):
    id: str
    project_id: str
    name: str
    base_url: str = ""
    variables: dict = {}
    secret_keys: list = []
    secret_masked: dict = {}
    is_default: bool = False
    is_prod: bool = False
    created_at: str = ""
    updated_at: str = ""


class APITestConfigResponse(BaseModel):
    test_case_id: str
    endpoint_id: Optional[str] = None
    method: str = "GET"
    url_template: str = ""
    headers: dict = {}
    query: dict = {}
    path_params: dict = {}
    body_text: str = ""
    auth: dict = {}
    expected_status: int = 200
    timeout_s: int = 30
    retry_network: bool = False
    spec_version: str = "v1"
    outdated_flag: bool = False
    is_setup: bool = False
    is_cleanup: bool = False
    extract_map: dict = {}
    assertions: list = []


class APIAssertionResponse(BaseModel):
    id: str
    test_case_id: str
    field: str
    target: str = ""
    operator: str = "eq"
    expected_value: Optional[str] = None
    status: str
    ai_generated: bool
    created_at: str = ""


class APIAssertionCreate(BaseModel):
    field: str = "status"
    target: str = ""
    operator: str = "eq"
    expected_value: Optional[str] = None


class APIAssertionUpdate(BaseModel):
    field: Optional[str] = None
    target: Optional[str] = None
    operator: Optional[str] = None
    expected_value: Optional[str] = None
    status: Optional[str] = None


# ---------- Phase 4: UI Automation ----------
class UIScriptResponse(BaseModel):
    test_case_id: str
    tc_code: str = ""
    flow: list = []
    script_text: str = ""
    script_version: int = 0
    status: str
    playwright_version: str = ""
    timeout_s: int = 180
    is_smoke: bool = False
    manual_preferred: bool = False
    manual_preferred_reason: Optional[str] = None
    flaky_flag: bool = False
    needs_mapping: bool = False
    policy_problems: list = []
    test_type: str = "WEB_UI"
    updated_by: Optional[str] = None
    update_reason: Optional[str] = None
    updated_at: str = ""


class UIScriptHistoryResponse(BaseModel):
    id: str
    version: int
    reason: Optional[str] = None
    changed_by: str
    created_at: str


class UIElementMappingCreate(BaseModel):
    page_name: str
    element_name: str
    locator: dict = {}
    fallback: Optional[dict] = None


class UIElementMappingResponse(BaseModel):
    id: str
    project_id: str
    page_name: str
    element_name: str
    locator: dict = {}
    fallback: Optional[dict] = None
    status: str
    used_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class UIPageCreate(BaseModel):
    page_name: str
    url_path: str = ""
    description: str = ""
    common_actions: list = []
    notes: Optional[str] = None


class UIPageResponse(BaseModel):
    id: str
    project_id: str
    page_name: str
    url_path: str = ""
    description: str = ""
    common_actions: list = []
    notes: Optional[str] = None
    element_count: int = 0
    created_at: str = ""
    updated_at: str = ""


# ---------- Phase 5: Regression Intelligence ----------
class ChangeCreate(BaseModel):
    source: str = "requirement_update"
    requirement_id: Optional[str] = None
    decision_id: Optional[str] = None
    bug_id: Optional[str] = None
    old_snapshot: Optional[dict] = None
    new_snapshot: Optional[dict] = None
    change_summary: Optional[str] = None
    hint: Optional[str] = None
    preferred_provider: Optional[str] = None
    model: Optional[str] = None


class ChangeResponse(BaseModel):
    id: str
    project_id: str
    change_code: str = ""
    source: str
    requirement_id: Optional[str] = None
    decision_id: Optional[str] = None
    bug_id: Optional[str] = None
    old_snapshot: dict = {}
    new_snapshot: dict = {}
    change_summary: str = ""
    business_summary: str = ""
    categories: list = []
    risk_level: str = "MEDIUM"
    risk_reasons: list = []
    status: str
    created_by: str = ""
    created_at: str = ""


class RegressionPlanCreate(BaseModel):
    change_ids: List[str] = []
    release_tag: Optional[str] = None
    time_budget_min: Optional[int] = None
    preferred_provider: Optional[str] = None
    model: Optional[str] = None


class RegressionPlanItemResponse(BaseModel):
    id: str
    test_case_id: str
    tc_code: str = ""
    title: str = ""
    tier: str
    reason: str = ""
    relationship_path: list = []
    risk: str = "MEDIUM"
    impact_confidence: str = "Medium"
    priority_rank: int = 999
    added_by: str = "ai"
    status: str = "PENDING"


class RegressionPlanResponse(BaseModel):
    id: str
    project_id: str
    plan_code: str = ""
    release_tag: Optional[str] = None
    status: str
    time_budget_min: Optional[int] = None
    test_run_id: Optional[str] = None
    change_codes: list = []
    item_count: int = 0
    must_count: int = 0
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""


# ---------- Phase 6: Data QA ----------
class DataSourceCreate(BaseModel):
    name: str
    kind: str = "file_csv"
    config: dict = {}


class DataSourceResponse(BaseModel):
    id: str
    project_id: str
    name: str
    kind: str
    config: dict = {}
    schema_fields: list = []
    created_by: str = ""
    created_at: str = ""


class DataJobCreate(BaseModel):
    name: str
    purpose: str = ""
    source_id: Optional[str] = None
    dest_id: Optional[str] = None
    requirement_id: Optional[str] = None
    build: str = ""
    environment: str = ""
    owner: Optional[str] = None
    key_fields: List[str] = []
    settings: dict = {}
    sync_tolerance_min: int = 0


class DataJobResponse(BaseModel):
    id: str
    project_id: str
    job_code: str = ""
    name: str
    purpose: str = ""
    source_id: Optional[str] = None
    dest_id: Optional[str] = None
    requirement_id: Optional[str] = None
    build: str = ""
    environment: str = ""
    owner: Optional[str] = None
    status: str
    key_fields: List[str] = []
    settings: dict = {}
    sync_tolerance_min: int = 0
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""


class FieldMappingCreate(BaseModel):
    source_field: str
    dest_field: str = ""
    transform: Optional[dict] = None
    ignored: bool = False


class FieldMappingResponse(BaseModel):
    id: str
    job_id: str
    source_field: str
    dest_field: str = ""
    transform: Optional[dict] = None
    ignored: bool = False
    status: str
    ai_suggested: bool = False
    created_at: str = ""


class DataRuleCreate(BaseModel):
    job_id: Optional[str] = None
    test_case_id: Optional[str] = None
    requirement_id: Optional[str] = None
    rule_type: str = "required"
    definition: dict = {}


class DataRuleResponse(BaseModel):
    id: str
    project_id: str
    job_id: Optional[str] = None
    test_case_id: Optional[str] = None
    requirement_id: Optional[str] = None
    rule_type: str
    definition: dict = {}
    status: str
    ai_generated: bool = False
    created_by: str = ""
    created_at: str = ""


class DataDifferenceResponse(BaseModel):
    id: str
    job_id: str
    execution_id: Optional[str] = None
    diff_type: str
    biz_key: str = ""
    field: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    severity: str = "MEDIUM"
    severity_reason: Optional[str] = None
    rule_id: Optional[str] = None
    evidence: dict = {}
    status: str = "OPEN"
    created_at: str = ""
