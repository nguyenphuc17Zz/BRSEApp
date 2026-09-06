export interface CandidateTranslation {
  text: string;
  style: string;
  confidence: number;
  reason?: string | null;
}

export interface UsedGlossaryItem {
  source_term: string;
  target_term: string;
  category?: string | null;
}

export interface UsedMemoryItem {
  source_text: string;
  target_text: string;
  similarity: number;
}

export interface TranslationResponse {
  result_id: string;
  session_id?: string;
  source_language: string;
  target_language: string;
  translations: CandidateTranslation[];
  ambiguity_detected: boolean;
  ambiguity_reason?: string | null;
  provider: string;
  model: string;
  latency_ms: number;
  qa_warnings: string[];
  used_glossary: UsedGlossaryItem[];
  used_memory: UsedMemoryItem[];
  detected_terms: Array<{ source: string; suggested: string }>;
}

export interface TranslationRequest {
  source_text: string;
  source_language?: string;
  target_language?: string;
  project_id?: string | null;
  style?: string;
  preferred_provider?: string;
  force_model?: string;
  session_id?: string;
  conversation_context?: string[];
}

export interface Project {
  id: string;
  name: string;
  code: string;
  description?: string;
  client_name?: string;
  source_language: string;
  target_language: string;
  default_style: string;
  is_active: boolean;
  created_at: string;
  instructions_count: number;
  glossary_count: number;
  tm_count: number;
}

export interface ProjectInstruction {
  id: string;
  project_id: string;
  rule_text: string;
  category: string;
  priority: number;
  is_active: boolean;
  created_at: string;
}

export interface GlossaryTerm {
  id: string;
  project_id?: string | null;
  project_name?: string | null;
  scope: string;
  source_term: string;
  target_term: string;
  source_language: string;
  target_language: string;
  definition?: string | null;
  category?: string | null;
  notes?: string | null;
  priority: number;
  is_active: boolean;
  created_at: string;
}

export interface TranslationMemoryItem {
  id: string;
  project_id?: string | null;
  project_name?: string | null;
  source_text: string;
  target_text: string;
  source_language: string;
  target_language: string;
  style?: string;
  provider?: string;
  model?: string;
  quality_signal: number;
  user_edited: boolean;
  created_at: string;
}

export interface HistoryItem {
  id: string;
  session_id?: string;
  project_id?: string;
  project_name?: string;
  source_text: string;
  selected_translation: string;
  candidate_translations: CandidateTranslation[];
  source_language: string;
  target_language: string;
  style: string;
  provider: string;
  model: string;
  latency_ms: number;
  ambiguity_detected: boolean;
  ambiguity_reason?: string;
  qa_warnings: string[];
  created_at: string;
}

export interface ProviderInfo {
  id: string;
  name: string;
  display_name: string;
  api_key_masked?: string;
  base_url?: string;
  default_model: string;
  available_models: string[];
  priority: number;
  is_enabled: boolean;
  is_healthy: boolean;
  health_message?: string;
  last_checked_at?: string;
}

export interface DashboardData {
  current_project?: Project | null;
  total_projects: number;
  total_glossary_terms: number;
  total_tm_entries: number;
  total_translations: number;
  recent_translations: any[];
  top_glossary_terms: GlossaryTerm[];
  providers_status: ProviderInfo[];
  recent_corrections: any[];
}

export interface DocumentItem {
  id: string;
  project_id?: string | null;
  filename: string;
  file_type: 'docx' | 'xlsx' | 'pptx' | 'pdf' | string;
  file_size: number;
  detected_language: string;
  unit_count: number;
  unit_label: string;
  created_at: string;
  active_job?: DocumentJob | null;
}

export interface DocumentJob {
  id: string;
  document_id: string;
  project_id?: string | null;
  status: 'queued' | 'analyzing' | 'segmenting' | 'translating' | 'qa' | 'rendering' | 'completed' | 'partially_completed' | 'failed' | 'cancelled' | 'paused';
  source_language: string;
  target_language: string;
  provider: string;
  model: string;
  style: string;
  total_segments: number;
  completed_segments: number;
  failed_segments: number;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
}

export interface DocumentSegment {
  id: string;
  job_id: string;
  segment_id: string;
  source_text: string;
  target_text?: string | null;
  translatable: boolean;
  unit_name?: string | null;
  unit_index: number;
  status: 'pending' | 'translated' | 'failed' | 'skipped';
  error_message?: string | null;
  user_edited: boolean;
  qa_status?: string | null;
  qa_issues?: any[] | null;
}

export interface DocumentIssue {
  id: string;
  job_id: string;
  segment_id?: string | null;
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  category: string;
  message: string;
  location?: string | null;
  created_at: string;
}

export interface DocumentProgress {
  job_id: string;
  status: string;
  progress_pct: number;
  total_segments: number;
  completed_segments: number;
  failed_segments: number;
  pending_segments: number;
  current_unit?: string | null;
  current_item?: string | null;
  qa_pct: number;
  elapsed_seconds: number;
}

export interface DocumentTranslateConfig {
  target_language?: string;
  project_id?: string | null;
  style?: string;
  provider?: string;
  model?: string;
  translate_notes?: boolean;
  use_ocr?: boolean;
  selected_units?: string[] | null;
}

// Phase 3: Workspace & Communication Integrations
export interface GoogleAccountItem {
  id: string;
  email: string;
  account_name: string;
  is_active: boolean;
  is_mock?: boolean;
  last_sync?: string | null;
}

export interface IntegrationHealth {
  google: {
    connected: boolean;
    account_name?: string | null;
    email?: string | null;
    is_mock: boolean;
    last_sync?: string | null;
    status: string;
    total_accounts?: number;
    accounts?: GoogleAccountItem[];
  };
  slack: {
    connected: boolean;
    workspace_name?: string | null;
    is_mock: boolean;
    mapped_channels: number;
    last_sync?: string | null;
    status: string;
  };
  desktop: {
    status: string;
    shortcuts: Record<string, string>;
    clipboard_available: boolean;
    active_window: {
      hwnd: number;
      title: string;
      process_name: string;
      pid: number;
    };
  };
  cache: {
    entries_count: number;
    retention_policy_days: number;
  };
}

export interface GoogleFileItem {
  id: string;
  name: string;
  mimeType: string;
  type: 'doc' | 'sheet' | 'slide' | 'folder' | string;
  parents?: string[];
  modifiedTime?: string;
  sharedDrive?: boolean;
  size?: string;
  sharedWithMeTime?: string;
  sharingUser?: {
    displayName?: string;
    emailAddress?: string;
    photoLink?: string;
  };
  owners?: Array<{
    displayName?: string;
    emailAddress?: string;
  }>;
}

export interface SlackChannel {
  id: string;
  name: string;
  is_private: boolean;
  topic?: string;
}

export interface SlackMessageAnalysis {
  category: string;
  tags: string[];
  priority_score: number;
  action_recommended: string;
}

export interface SlackMessage {
  ts: string;
  user: string;
  username?: string;
  text: string;
  thread_ts?: string;
  reply_count?: number;
  analysis?: SlackMessageAnalysis;
}

export interface SlackReplyOption {
  style: string;
  text: string;
  description: string;
}

export interface ChannelMapping {
  id: string;
  account_id: string;
  channel_id: string;
  channel_name: string;
  project_id?: string | null;
  auto_translate: boolean;
  min_priority_score: number;
}

export interface QuickTranslateResult {
  source_text: string;
  translation: string;
  candidate_translations?: any[];
  active_app?: string;
  window_title?: string;
  applied_style?: string;
  qa_warnings?: string[];
  used_glossary?: any[];
  used_memory?: any[];
}

// Phase 4 — BrSE Brain & Intelligence Types
export interface WorkItemEvidence {
  id: string;
  source_type: string;
  source_id: string;
  quote_text: string;
  author?: string | null;
  timestamp?: string | null;
  confidence: number;
  confirmation_status: string;
}

export interface WorkItem {
  id: string;
  project_id: string;
  item_type: 'REQUIREMENT' | 'BUG' | 'QUESTION' | 'DECISION' | 'TODO' | 'RISK' | 'DEADLINE' | 'DEPENDENCY' | 'OPEN_QUESTION' | 'MEETING_ITEM';
  title: string;
  description: string;
  details_json: string;
  status: 'PROPOSED' | 'CONFIRMED' | 'IN_PROGRESS' | 'BLOCKED' | 'DONE' | 'REJECTED' | 'SUPERSEDED' | 'NEEDS_CONFIRMATION' | 'CONFLICT';
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  assignee?: string | null;
  deadline_date?: string | null;
  confidence: number;
  version: number;
  is_conflict: boolean;
  conflict_notes?: string | null;
  created_at: string;
  updated_at: string;
  evidence_items?: WorkItemEvidence[];
}

export interface DashboardMetrics {
  urgent_count: number;
  open_questions_count: number;
  deadlines_count: number;
  completed_count: number;
  conflicts_count: number;
  proposed_requirements_count: number;
  unresolved_bugs_count: number;
  recent_decisions_count: number;
  total_items: number;
}

export interface WorkInboxItem {
  id: string;
  project_id: string;
  type: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  confidence: number;
  is_conflict: boolean;
  conflict_notes?: string | null;
  deadline_date?: string | null;
  assignee?: string | null;
  created_at: string;
  meeting_id?: string | null;
  meeting_title?: string | null;
  meeting_date?: string | null;
  source_type?: string;
  author?: string | null;
  evidence: Array<{ source_type: string; quote: string; author?: string }>;
}

export interface WorkInboxResponse {
  total_pending: number;
  meetings?: Array<{ id: string; title: string; date: string }>;
  requirements: WorkInboxItem[];
  bugs: WorkInboxItem[];
  decisions: WorkInboxItem[];
  questions: WorkInboxItem[];
  deadlines: WorkInboxItem[];
}

export interface AskProjectCitation {
  source_type?: string;
  source?: string;
  id?: string;
  title?: string;
  quote: string;
  author?: string;
  date?: string;
}

export interface AskProjectResponse {
  answer: string;
  confidence: number;
  citations: AskProjectCitation[];
  known_unknowns: string[];
  follow_up_suggestions?: string[];
}

export interface ProjectBrainStats {
  project_id: string;
  total_meetings: number;
  total_work_items: number;
  total_decisions: number;
  total_actions: number;
  total_open_questions: number;
  total_evidences: number;
  is_synced: boolean;
}

export interface DocumentDiffResponse {
  added: Array<{ item: string; description: string }>;
  removed: Array<{ item: string; description: string }>;
  modified: Array<{ item: string; before: string; after: string; significance: string }>;
  conflicts: Array<{ issue: string; recommendation: string }>;
}

export interface ImpactAnalysisResponse {
  impacted_apis: string[];
  impacted_frontend: string[];
  impacted_tests: string[];
  database_impact: string;
  schedule_risk: string;
  recommended_actions: string[];
}

export interface SmartReplyOption {
  style: string;
  text: string;
  rationale: string;
}

export interface SmartReplyResponse {
  detected_intent: string;
  commitment_warning?: string | null;
  replies: SmartReplyOption[];
}

export interface MeetingItemRecord {
  id: string;
  project_id?: string;
  title: string;
  meeting_date: string;
  participants?: string[];
  summary_markdown: string;
  summary_ja?: string;
  summary_vi?: string;
  decisions: Array<{
    title?: string;
    title_ja?: string;
    title_vi?: string;
    detail?: string;
    detail_ja?: string;
    detail_vi?: string;
    evidence?: string;
  }>;
  action_items: Array<{
    task?: string;
    task_ja?: string;
    task_vi?: string;
    assignee?: string;
    due_date?: string;
    priority?: string;
  }>;
  open_questions: Array<{
    question?: string;
    question_ja?: string;
    question_vi?: string;
    owner?: string;
    urgency?: string;
  }>;
  created_at: string;
}

export interface LineRagSource {
  file_name: string;
  chunk_index: number;
  snippet?: string;
}

export interface LineMessageItem {
  id?: string;
  source?: string;
  project_id?: string | null;
  conversation_id: string;
  message_id: string;
  sender: string;
  sender_id?: string | null;
  timestamp: string;
  text: string;
  reply_token?: string;
  detected_intent?: string;
  commitment_warning?: string | null;
  suggested_replies?: SmartReplyOption[];
  rag_sources?: LineRagSource[];
  sync_result?: {
    requirements?: number;
    bugs?: number;
    decisions?: number;
    deadlines?: number;
    work_items_count?: number;
    [key: string]: any;
  };
  created_at?: string;
}

export interface SlackMessageItem {
  source: string;
  channel: string;
  message_id: string;
  sender: string;
  timestamp: string;
  text: string;
  thread_ts?: string | null;
  detected_intent?: string;
  suggested_replies?: SmartReplyOption[];
}

export interface AutomationRuleItem {
  id: string;
  project_id?: string | null;
  name: string;
  event_trigger: string;
  condition_json: string;
  action_type: string;
  is_active: boolean;
  created_at: string;
}

export interface ProjectStakeholder {
  id: string;
  project_id: string;
  name: string;
  role: string;
  organization: string;
  platform?: string;
  notes?: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface StakeholderCreatePayload {
  project_id: string;
  name: string;
  role?: string;
  organization?: string;
  platform?: string;
  notes?: string;
}


