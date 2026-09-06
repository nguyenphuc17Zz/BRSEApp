# AI Comtor / BrSE Copilot (Phase 1)

> **Enterprise-grade Japanese ↔ Vietnamese Translation & Knowledge Copilot for IT Communicators & Bridge Software Engineers (BrSE)**

---

## 1. Product Overview

AI Comtor / BrSE Copilot is a **local-first Windows application** engineered specifically for the rigorous demands of Japanese-Vietnamese IT projects. It eliminates the limitations of generic machine translation tools by introducing:

- **Project-Specific Workspaces:** Dynamic prompt injection of client rules, project guidelines, and technical constraints.
- **Hierarchical Glossary Engine:** Terminology enforcement across Project, Client, Company, and Global scopes.
- **Translation Memory (TM) with Hybrid Search:** Exact/lexical matching combined with local vector embeddings (`nomic-embed-text` via Ollama) and cosine similarity.
- **Multi-Provider AI Orchestration:** Provider abstraction supporting **Google Gemini**, **Groq Cloud**, and local offline **Ollama** with automated priority-based failover.
- **Ambiguity Detection & Multi-Candidate Output:** Returns 2–3 categorized options when ambiguous Japanese phrasing is detected (e.g. `対象外`, `対応`, `検討`).
- **Translation QA Checks:** Automated verification preserving numbers, URLs, code identifiers, and mandatory glossary terms.
- **Continuous Correction Learning:** Saves human corrections to project memory, automatically influencing subsequent AI translation context.
- **Comtor Productivity Tools:** Integrated **Explain** (grammar nuances & IT terms breakdown) and **Reply Generator** (polite, business, natural reply suggestions).

---

## 2. System Architecture

```text
Windows Environment
│
├── Local Backend Service (FastAPI + SQLAlchemy + SQLite)
│   ├── AI Orchestrator & Modular Prompt Builder
│   ├── Dynamic Provider Router (Gemini / Groq / Ollama)
│   ├── Context Engine (Project Rules, Glossary, TM, Corrections)
│   ├── Translation QA Engine (Number, URL, Terminology integrity)
│   ├── Security Service (AES-256 Fernet Encrypted Credentials + PII Masking)
│   └── Local SQLite Database (WAL Mode + FTS5)
│
└── Web UI (React 18 + TypeScript + Vite + Tailwind CSS)
    ├── Dashboard (Real-time operational metrics & provider health)
    ├── Translator (Bidirectional JA↔VI, Style Presets, Multi-Option Candidates)
    ├── Projects (Client rules & workspace manager)
    ├── Glossary (Hierarchical terminology repository)
    ├── Translation Memory (Searchable segments & verified references)
    ├── History & Audit Logs (Traceability of prompt context & models used)
    ├── AI Providers (Connection testing & model router priority)
    └── Settings (Platform configuration & Phase 2 extension points)
```

---

## 3. Quick Start (1-Click Run)

### Option A: 1-Click Batch File (Recommended on Windows)
Simply double-click:
```bat
start.bat
```
This script will:
1. Initialize the Python virtual environment if needed.
2. Start the FastAPI backend at `http://127.0.0.1:8000`.
3. Start the Vite React UI at `http://127.0.0.1:5173`.
4. Open your default browser to the copilot interface.

### Option B: PowerShell Launcher
```powershell
.\run.ps1
```

---

## 4. Manual Setup & Development

### Backend Service
1. Navigate to the backend directory:
   ```bash
   cd services/backend
   ```
2. Activate the virtual environment:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Initialize the SQLite database and seed demo data:
   ```bash
   python -m app.db.seed
   ```
5. Start the backend server:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   API Swagger Docs available at: `http://127.0.0.1:8000/docs`

### Frontend Application
1. Navigate to the web directory:
   ```bash
   cd apps/web
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start Vite development server:
   ```bash
   npm run dev
   ```
   Access the UI at `http://127.0.0.1:5173`.

---

## 5. Environment Variables & Configuration

The backend reads configuration from `services/backend/.env`:

| Key | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite+aiosqlite:///../../data/comtor_copilot.db` | Local SQLite database file location |
| `SECRET_KEY` | (Secure salt) | Key derivation salt for AES-256 Fernet credential encryption |
| `GEMINI_API_KEY` | Configured | Google Gemini API key (encrypted in DB) |
| `GROQ_API_KEY` | Configured | Groq Cloud API key (encrypted in DB) |
| `OLLAMA_BASE_URL`| `http://127.0.0.1:11434` | Local Ollama REST endpoint |
| `OLLAMA_DEFAULT_MODEL`| `gemma4:12b` | Default local model fallback |
| `OLLAMA_EMBED_MODEL`| `nomic-embed-text:latest` | Local vector embedding model for Translation Memory |

---

## 6. Testing & Definition of Done (DoD) Verification

Run all unit and scenario tests with:
```bat
test.bat
```
Or via terminal:
```bash
cd services/backend
.\.venv\Scripts\pytest.exe -v
```

### Verified Scenarios:
- **Scenario A (Project + Glossary + History):** Verified project `ABC Banking System` applies mandatory glossary term `認証` → `Authentication`, applies project instructions, and records translation history.
- **Scenario B (Ambiguity Detection):** Verified `この件は対象外です。` triggers ambiguity analysis, returning multiple candidate options with register and reasoning.
- **Scenario C (User Correction Learning):** Verified user corrections are persisted in database and dynamically injected into future translation context packages.
- **Scenario D & E (Provider Registry & Fallback):** Verified all three providers (`gemini`, `groq`, `ollama`) are initialized and failover sequentially in case of provider quota or network issues.

---

## 7. Phase 2–4 Extension Points

Phase 1 provides clean abstraction interfaces in the architecture for subsequent phases:
- **Phase 2 (File & Document Processing):** Abstracted `DocumentSource` interface ready for `.docx`, `.xlsx`, `.pptx`, `.pdf`, and OCR pipeline.
- **Phase 3 (Chat & Cloud Integration):** Abstracted `ConversationContext` interface ready for Slack webhooks, Google Docs / Sheets add-on, and Windows global clipboard listener.
- **Phase 4 (Advanced BrSE Copilot):** Foundation ready for requirement defect detection, meeting minutes action-item extraction, and automated Japanese reply drafting.
