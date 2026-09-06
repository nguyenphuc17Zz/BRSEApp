import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

# --- Document Translation Start Request ---
class DocumentTranslationStartRequest(BaseModel):
    target_language: str = Field(default="vi")
    source_language: str = Field(default="ja")
    project_id: Optional[str] = None
    style: str = Field(default="business")
    provider: str = Field(default="gemini")
    model: str = Field(default="gemini-3.5-flash-lite")
    selected_sheets: Optional[Union[str, List[str]]] = None
    selected_units: Optional[List[str]] = None
    translate_notes: bool = True
    use_ocr: bool = False
    custom_output_dir: Optional[str] = None

# --- Translation Models ---
class CandidateTranslation(BaseModel):
    text: str
    style: str = "business"
    confidence: float = 0.95
    reason: Optional[str] = None

class UsedGlossaryItem(BaseModel):
    source_term: str
    target_term: str
    category: Optional[str] = None

class UsedMemoryItem(BaseModel):
    source_text: str
    target_text: str
    similarity: float

class TranslationRequest(BaseModel):
    source_text: str = Field(..., min_length=1, description="Text to be translated")
    source_language: str = Field(default="auto", description="ja, vi, or auto")
    target_language: str = Field(default="vi", description="vi, ja, etc.")
    project_id: Optional[str] = None
    style: str = Field(default="auto", description="auto, natural, technical, business, very_polite, casual, customer_facing, internal, concise")
    preferred_provider: Optional[str] = None
    force_model: Optional[str] = None
    session_id: Optional[str] = None
    conversation_context: Optional[List[str]] = None

class TranslationResponse(BaseModel):
    result_id: str
    session_id: Optional[str] = None
    source_language: str
    target_language: str
    translations: List[CandidateTranslation]
    ambiguity_detected: bool = False
    ambiguity_reason: Optional[str] = None
    provider: str
    model: str
    latency_ms: int
    qa_warnings: List[str] = []
    used_glossary: List[UsedGlossaryItem] = []
    used_memory: List[UsedMemoryItem] = []
    detected_terms: List[Dict[str, str]] = []

# --- Explain & Reply & Rewrite ---
class ExplainRequest(BaseModel):
    source_text: str
    translation_text: str
    source_language: str = "ja"
    target_language: str = "vi"
    project_id: Optional[str] = None
    preferred_provider: Optional[str] = None
    force_model: Optional[str] = None

class ExplainResponse(BaseModel):
    summary: str
    grammar_and_nuances: List[str]
    technical_terms: List[Dict[str, str]]
    alternative_interpretations: List[str]

class ReplyOption(BaseModel):
    style: str # normal, polite, very_polite, concise, natural
    text: str
    notes: Optional[str] = None

class ReplyRequest(BaseModel):
    source_message: str
    user_intent: Optional[str] = None
    conversation_history: Optional[List[str]] = None
    project_id: Optional[str] = None
    reply_language: str = "ja" # Usually responding back in Japanese
    preferred_provider: Optional[str] = None
    force_model: Optional[str] = None

class ReplyResponse(BaseModel):
    options: List[ReplyOption]

class RewriteRequest(BaseModel):
    text: str
    tone: str # polite, natural, shorter, softer, stronger, business
    language: str = "ja"
    project_id: Optional[str] = None
    preferred_provider: Optional[str] = None
    force_model: Optional[str] = None

class RewriteResponse(BaseModel):
    original_text: str
    rewritten_text: str
    tone: str

# --- Project Models ---
class ProjectCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    client_name: Optional[str] = None
    source_language: str = "ja"
    target_language: str = "vi"
    default_style: str = "business"
    instructions: Optional[List[str]] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    client_name: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    default_style: Optional[str] = None
    is_active: Optional[bool] = None

class ProjectInstructionCreate(BaseModel):
    rule_text: str
    category: str = "general"
    priority: int = 1

class ProjectInstructionResponse(BaseModel):
    id: str
    project_id: str
    rule_text: str
    category: str
    priority: int
    is_active: bool
    created_at: datetime.datetime

class ProjectResponse(BaseModel):
    id: str
    name: str
    code: str
    description: Optional[str] = None
    client_name: Optional[str] = None
    source_language: str
    target_language: str
    default_style: str
    is_active: bool
    created_at: datetime.datetime
    instructions_count: int = 0
    glossary_count: int = 0
    tm_count: int = 0

# --- Glossary Models ---
class GlossaryTermCreate(BaseModel):
    project_id: Optional[str] = None
    scope: str = "project" # global, company, client, project, personal
    source_term: str
    target_term: str
    source_language: str = "ja"
    target_language: str = "vi"
    definition: Optional[str] = None
    category: Optional[str] = "IT"
    notes: Optional[str] = None
    priority: int = 1

class GlossaryTermUpdate(BaseModel):
    source_term: Optional[str] = None
    target_term: Optional[str] = None
    definition: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None

class GlossaryTermResponse(BaseModel):
    id: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    scope: str
    source_term: str
    target_term: str
    source_language: str
    target_language: str
    definition: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    priority: int
    is_active: bool
    created_at: datetime.datetime

# --- Translation Memory Models ---
class TranslationMemoryCreate(BaseModel):
    project_id: Optional[str] = None
    source_text: str
    target_text: str
    source_language: str = "ja"
    target_language: str = "vi"
    style: Optional[str] = "business"
    provider: Optional[str] = None
    model: Optional[str] = None
    quality_signal: float = 1.0
    user_edited: bool = False

class TranslationMemoryResponse(BaseModel):
    id: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    source_text: str
    target_text: str
    source_language: str
    target_language: str
    style: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    quality_signal: float
    user_edited: bool
    created_at: datetime.datetime

# --- Correction Models ---
class CorrectionCreate(BaseModel):
    project_id: Optional[str] = None
    source_text: str
    original_translation: str
    corrected_translation: str
    language_pair: str = "ja-vi"
    context_note: Optional[str] = None
    apply_scope: str = "project" # project, global
    save_to_tm: bool = True

class CorrectionResponse(BaseModel):
    id: str
    project_id: Optional[str] = None
    source_text: str
    original_translation: str
    corrected_translation: str
    language_pair: str
    context_note: Optional[str] = None
    apply_scope: str
    created_at: datetime.datetime

# --- Provider Models ---
class ProviderCreate(BaseModel):
    name: str # gemini, groq, ollama
    display_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str
    priority: int = 1
    is_enabled: bool = True

class ProviderUpdate(BaseModel):
    display_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None

class ProviderResponse(BaseModel):
    id: str
    name: str
    display_name: str
    api_key_masked: Optional[str] = None
    base_url: Optional[str] = None
    default_model: str
    available_models: List[str] = []
    priority: int
    is_enabled: bool
    is_healthy: bool
    health_message: Optional[str] = None
    last_checked_at: Optional[datetime.datetime] = None

# --- Dashboard Stats ---
class DashboardStats(BaseModel):
    current_project: Optional[ProjectResponse] = None
    total_projects: int
    total_glossary_terms: int
    total_tm_entries: int
    total_translations: int
    recent_translations: List[Any] = []
    top_glossary_terms: List[GlossaryTermResponse] = []
    providers_status: List[ProviderResponse] = []
    recent_corrections: List[CorrectionResponse] = []
