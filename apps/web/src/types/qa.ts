// QA Workspace Phase 1 types
export type KnowledgeClass = 'Confirmed' | 'Inferred' | 'AISuggested';

export interface QAFinding {
  id: string;
  project_id: string;
  requirement_id: string;
  title: string;
  description: string;
  finding_type: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string;
  confidence: number;
  evidence_quote: string;
  evidence_source_type: string;
  evidence_source_id: string;
  knowledge_class: KnowledgeClass | string;
  suggested_action?: string | null;
  status: 'OPEN' | 'RESOLVED' | 'IGNORED' | string;
  ai_generated: boolean;
  created_at: string;
  updated_at: string;
}

export interface QAOpenQuestion {
  id: string;
  project_id: string;
  requirement_id: string;
  finding_id?: string | null;
  question_vi: string;
  question_ja: string;
  reason: string;
  evidence_quote: string;
  risk_if_unanswered?: string | null;
  status: 'DRAFT' | 'APPROVED' | 'ANSWERED' | 'REJECTED' | string;
  answer_text?: string | null;
  ai_generated: boolean;
  created_at: string;
  updated_at: string;
}

export interface AcceptanceCriterion {
  id: string;
  project_id: string;
  requirement_id: string;
  ac_code: string;
  given_text: string;
  when_text: string;
  then_text: string;
  knowledge_class: KnowledgeClass | string;
  evidence_quote: string;
  status: 'DRAFT' | 'APPROVED' | 'REJECTED' | string;
  ai_generated: boolean;
  created_at: string;
  updated_at: string;
}

export interface QATestStep {
  id: string;
  step_order: number;
  action: string;
  expected: string;
}

export interface QATestCase {
  id: string;
  project_id: string;
  tc_code: string;
  title: string;
  purpose: string;
  case_type: string;
  priority: string;
  preconditions: string;
  expected_result: string;
  requirement_id: string;
  acceptance_criterion_id?: string | null;
  evidence_quote: string;
  knowledge_class: KnowledgeClass | string;
  source: string;
  ai_generated: boolean;
  confidence: number;
  status: 'DRAFT' | 'REVIEWED' | 'APPROVED' | 'REJECTED' | string;
  steps: QATestStep[];
  created_at: string;
  updated_at: string;
}

export interface RequirementCoverage {
  project_id: string;
  requirement_id: string;
  requirement_title: string;
  req_code?: string | null;
  has_review: boolean;
  findings_open: number;
  questions_unanswered: number;
  ac_total: number;
  ac_approved: number;
  tc_total: number;
  tc_approved: number;
  status: 'NotReviewed' | 'NotCovered' | 'PartiallyCovered' | 'Covered' | 'BlockedByClarification' | string;
  computed_at: string;
}

export interface QARequirement {
  id: string;
  project_id: string;
  req_code?: string | null;
  title: string;
  description: string;
  status: string;
  priority: string;
  evidence_count: number;
  coverage: string;
  findings_open: number;
  questions_unanswered: number;
  ac_total: number;
  tc_total: number;
}

export interface QAOverview {
  project_id?: string | null;
  total_requirements: number;
  reviewed_requirements: number;
  needs_clarification: number;
  open_questions: number;
  unapproved_ac: number;
  covered_requirements: number;
  uncovered_requirements: number;
  testcase_draft: number;
  testcase_approved: number;
  active_runs?: number;
  exec_pass?: number;
  exec_fail?: number;
  exec_blocked?: number;
  exec_not_run?: number;
  open_bugs?: number;
  retest_pending?: number;
  latest_build?: string | null;
  latest_build_status?: string | null;
  api_tests?: number;
  api_pass?: number;
  api_fail?: number;
  api_endpoints?: number;
  api_endpoints_covered?: number;
  api_recent_failures?: Array<{ execution_id: string; tc_code: string; title: string }>;
  ui_automated?: number;
  ui_pass?: number;
  ui_fail?: number;
  changes_pending?: number;
  regression_required?: number;
  regression_in_progress?: number;
  high_risk_changes?: number;
  tests_needing_update?: number;
  data_jobs?: number;
  data_records?: number;
  data_differences?: number;
  data_violations?: number;
  data_missing?: number;
  data_failures?: number;
}

export interface RequirementDetail {
  id: string;
  project_id: string;
  req_code?: string | null;
  title: string;
  description: string;
  status: string;
  priority: string;
  evidence_items: Array<{
    id: string;
    source_type: string;
    source_id: string;
    quote_text: string;
    author?: string | null;
    timestamp?: string | null;
    confidence: number;
    confirmation_status: string;
  }>;
  findings: QAFinding[];
  questions: QAOpenQuestion[];
  acceptance_criteria: AcceptanceCriterion[];
  test_cases: QATestCase[];
  coverage?: RequirementCoverage | null;
  exec_summary?: ExecSummary | null;
  related_bugs?: RelatedBug[] | null;
  case_history?: CaseHistoryItem[] | null;
}

// QA Workspace Phase 2 types
export interface RunProgress {
  total: number;
  not_run: number;
  pass: number;
  fail: number;
  blocked: number;
  skipped: number;
  executed: number;
}

export interface TestRun {
  id: string;
  project_id: string;
  run_code: string;
  name: string;
  version_build: string;
  environment: string;
  scope: Record<string, any>;
  start_date?: string | null;
  end_date?: string | null;
  tester?: string | null;
  status: 'DRAFT' | 'READY' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | string;
  run_type?: string;
  notes?: string | null;
  progress: RunProgress;
  created_at: string;
  updated_at: string;
}

export interface TestExecution {
  id: string;
  test_run_id: string;
  test_case_id: string;
  tc_code: string;
  tc_title: string;
  requirement_id: string;
  req_code?: string | null;
  acceptance_criterion_id?: string | null;
  attempt_no: number;
  prev_execution_id?: string | null;
  status: 'NOT_RUN' | 'RUNNING' | 'PASS' | 'FAIL' | 'BLOCKED' | 'SKIPPED' | string;
  actual_result?: string | null;
  notes?: string | null;
  fail_reason?: string | null;
  tester?: string | null;
  executed_at?: string | null;
  bug_work_item_id?: string | null;
  bug_code?: string | null;
  evidence_count: number;
  created_at: string;
  updated_at: string;
}

export interface TestEvidence {
  id: string;
  execution_id: string;
  test_case_id: string;
  requirement_id: string;
  bug_work_item_id?: string | null;
  evidence_type: string;
  title: string;
  text_content?: string | null;
  file_path?: string | null;
  mime_type?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface BugDetail {
  id: string;
  project_id: string;
  bug_code?: string | null;
  title: string;
  description: string;
  details: Record<string, any>;
  status: string;
  ux_status: string;
  priority: string;
  assignee?: string | null;
  requirement_id?: string | null;
  req_code?: string | null;
  requirement_title?: string | null;
  test_case_id?: string | null;
  tc_code?: string | null;
  test_case_title?: string | null;
  test_run_id?: string | null;
  run_code?: string | null;
  execution_id?: string | null;
  evidence: Array<{ id: string; source_type: string; quote_text: string; author?: string | null }>;
  retests: Array<{ id: string; attempt_no: number; status: string }>;
  created_at: string;
  updated_at: string;
}

export interface ExecSummary {
  exec_total: number;
  exec_executed: number;
  exec_passed: number;
  exec_failed: number;
  exec_blocked: number;
  exec_status: string;
  last_result?: string | null;
  last_build?: string | null;
}

export interface RelatedBug {
  id: string;
  bug_code?: string | null;
  title: string;
  status: string;
  ux_status: string;
}

export interface CaseHistoryItem {
  tc_code: string;
  status: string;
  attempt_no: number;
  build: string;
  run_code: string;
  bug_code?: string | null;
}

// QA Phase 3: API testing types
export interface APIEndpoint {
  id: string;
  project_id: string;
  method: string;
  path: string;
  name: string;
  description: string;
  auth_type: string;
  parameters: any[];
  request_body: any;
  responses: any;
  tags: string[];
  requirement_id?: string | null;
  req_code?: string | null;
  spec_source: string;
  spec_version: string;
  test_case_count: number;
  last_result?: string | null;
  last_build?: string | null;
  created_at: string;
  updated_at: string;
}

export interface APIEnvironment {
  id: string;
  project_id: string;
  name: string;
  base_url: string;
  variables: Record<string, any>;
  secret_keys: string[];
  secret_masked: Record<string, string>;
  is_default: boolean;
  is_prod: boolean;
  created_at: string;
  updated_at: string;
}

export interface APIAssertion {
  id: string;
  test_case_id: string;
  field: string;
  target: string;
  operator: string;
  expected_value?: string | null;
  status: string;
  ai_generated: boolean;
  created_at: string;
}

export interface APITestConfig {
  test_case_id: string;
  endpoint_id?: string | null;
  method: string;
  url_template: string;
  headers: Record<string, any>;
  query: Record<string, any>;
  path_params: Record<string, any>;
  body_text: string;
  auth: Record<string, any>;
  expected_status: number;
  timeout_s: number;
  retry_network: boolean;
  spec_version: string;
  outdated_flag: boolean;
  is_setup: boolean;
  is_cleanup: boolean;
  extract_map: Record<string, string>;
  assertions: APIAssertion[];
}

export interface APITestCase {
  id: string;
  project_id: string;
  tc_code: string;
  title: string;
  purpose: string;
  case_type: string;
  priority: string;
  status: string;
  knowledge_class: string;
  requirement_id: string;
  api_config?: APITestConfig | null;
  last_result?: string | null;
  requirement?: { id: string; req_code?: string | null; title: string } | null;
  history?: Array<{ status: string; attempt_no: number; build: string; run_code: string; bug_id?: string | null; at: string }>;
}

export interface APIFlow {
  id: string;
  project_id: string;
  name: string;
  description: string;
  step_case_ids: string[];
  setup_case_id?: string | null;
  cleanup_case_id?: string | null;
}

export interface QAReport {
  id: string;
  project_id: string;
  test_run_id?: string | null;
  report_type: string;
  scope_build: string;
  markdown_vi: string;
  markdown_ja: string;
  metrics: Record<string, any>;
  status: string;
  ai_generated: boolean;
  created_at: string;
}

// QA Phase 4: UI automation types
export interface UIFlowStep {
  order: number;
  label: string;
  action: string;
  mapping_id?: string | null;
  target?: { strategy: string; value: string; options?: any } | null;
  value?: any;
  assertion_source?: string;
  checkpoint?: boolean;
  selector_required?: boolean;
  element_hint?: string;
}

export interface UIScript {
  test_case_id: string;
  tc_code: string;
  title?: string;
  requirement_id?: string | null;
  flow: UIFlowStep[];
  script_text: string;
  script_version: number;
  status: string;
  playwright_version: string;
  timeout_s: number;
  is_smoke: boolean;
  manual_preferred: boolean;
  manual_preferred_reason?: string | null;
  flaky_flag: boolean;
  needs_mapping: boolean;
  policy_problems: string[];
  test_type: string;
  last_result?: string | null;
  updated_by?: string | null;
  update_reason?: string | null;
  updated_at: string;
  requirement?: { id: string; req_code?: string | null; title: string } | null;
  history?: Array<{ id: string; version: number; reason?: string | null; changed_by: string; created_at: string }>;
  flaky?: { sequence: string[]; alternations: number; flaky: boolean; label: string };
}

export interface UIElementMapping {
  id: string;
  project_id: string;
  page_name: string;
  element_name: string;
  locator: { strategy: string; value: string; options?: any };
  fallback?: any;
  status: string;
  used_count: number;
  created_at: string;
  updated_at: string;
}

export interface UIPage {
  id: string;
  project_id: string;
  page_name: string;
  url_path: string;
  description: string;
  common_actions: string[];
  notes?: string | null;
  element_count: number;
  created_at: string;
  updated_at: string;
}

// QA Phase 5: Regression Intelligence types
export interface ChangeRecord {
  id: string;
  project_id: string;
  change_code: string;
  source: string;
  requirement_id?: string | null;
  decision_id?: string | null;
  bug_id?: string | null;
  old_snapshot: any;
  new_snapshot: any;
  change_summary: string;
  business_summary: string;
  categories: string[];
  risk_level: string;
  risk_reasons: string[];
  status: string;
  created_by: string;
  created_at: string;
  plan_ids?: string[];
}

export interface RegressionPlanItem {
  id: string;
  test_case_id: string;
  tc_code: string;
  title: string;
  tier: string;
  reason: string;
  relationship_path: string[];
  risk: string;
  impact_confidence: string;
  priority_rank: number;
  added_by: string;
  status: string;
}

export interface RegressionPlan {
  id: string;
  project_id: string;
  plan_code: string;
  release_tag?: string | null;
  status: string;
  time_budget_min?: number | null;
  test_run_id?: string | null;
  change_codes: string[];
  item_count: number;
  must_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  items?: RegressionPlanItem[];
  changes?: ChangeRecord[];
}

// QA Phase 6: Data QA types
export interface DataSource {
  id: string;
  project_id: string;
  name: string;
  kind: string;
  config: Record<string, any>;
  schema_fields: string[];
  created_by: string;
  created_at: string;
}

export interface DataJob {
  id: string;
  project_id: string;
  job_code: string;
  name: string;
  purpose: string;
  source_id?: string | null;
  dest_id?: string | null;
  requirement_id?: string | null;
  build: string;
  environment: string;
  owner?: string | null;
  status: string;
  key_fields: string[];
  settings: Record<string, any>;
  sync_tolerance_min: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface FieldMapping {
  id: string;
  job_id: string;
  source_field: string;
  dest_field: string;
  transform?: Record<string, any> | null;
  ignored: boolean;
  status: string;
  ai_suggested: boolean;
  created_at: string;
}

export interface DataRule {
  id: string;
  project_id: string;
  job_id?: string | null;
  test_case_id?: string | null;
  requirement_id?: string | null;
  rule_type: string;
  definition: Record<string, any>;
  status: string;
  ai_generated: boolean;
  created_by: string;
  created_at: string;
}

export interface DataDifference {
  id: string;
  job_id: string;
  execution_id?: string | null;
  diff_type: string;
  biz_key: string;
  field?: string | null;
  expected?: string | null;
  actual?: string | null;
  severity: string;
  severity_reason?: string | null;
  rule_id?: string | null;
  evidence: Record<string, any>;
  status: string;
  created_at: string;
}
