# AI COMTOR & BrSE COPILOT — ARCHITECTURE & PROJECT CONTEXT
> **Mục đích tài liệu:** Bản tài liệu tổng quan toàn diện (Master Context) dành cho ChatGPT / LLMs để nắm trọn vẹn nghiệp vụ, kiến trúc công nghệ, luồng xử lý, cấu trúc code và schema cơ sở dữ liệu của dự án.

---

## 1. TỔNG QUAN DỰ ÁN & BÀI TOÁN NGHIỆP VỤ

### 1.1. Tên dự án & Định vị sản phẩm
- **Tên dự án:** **AI Comtor / BrSE Copilot**
- **Định vị:** Enterprise-grade Japanese ↔ Vietnamese Translation & Knowledge Copilot for IT Communicators (Comtor) & Bridge Software Engineers (BrSE).
- **Môi trường vận hành:** Ứng dụng Desktop/Web Local-First trên nền tảng Windows, ưu tiên bảo mật dữ liệu khách hàng, hỗ trợ dịch offline (qua Ollama) kết hợp online (Google Gemini, Groq Cloud).

### 1.2. Đối tượng sử dụng & Vấn đề giải quyết
1. **IT Comtor (IT Communicator):**
   - Dịch thuật tài liệu đặc tả (BRD, SRS, Screen Transition, API Spec, Database Schema) từ tiếng Nhật sang tiếng Việt và ngược lại.
   - Vấn đề gặp phải với Google Translate thông thường: Dịch sai thuật ngữ chuyên ngành IT, làm mất công thức Excel, hỏng format/layout PDF/Word, không nhớ ngữ cảnh dự án/khách hàng.
2. **BrSE (Bridge Software Engineer):**
   - Quản lý yêu cầu, biên bản cuộc họp (Meeting Minutes), làm rõ yêu cầu mập mờ (Q&A), phân tích tác động thay đổi spec, theo dõi cam kết deadline và phòng ngừa rủi ro hiểu nhầm giữa khách hàng Nhật và đội ngũ Offshore Việt Nam.
   - Giao tiếp tức thời qua Slack, LINE, Chatwork với khách hàng Nhật: Cần văn phong kính ngữ chuẩn xác (Keigo - Sonkeigo, Kenjougo, Teineigo), tránh tự ý cam kết deadline (Commitment Protection).

---

## 2. KIẾN TRÚC HỆ THỐNG & TECH STACK

### 2.1. Sơ đồ kiến trúc tổng quan
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND (React 19 + Vite)                       │
│  - 15 Modules: Translator, Documents, Integrations, BrSE Workspace,        │
│    Project Brain & RAG, Meeting Minutes, LINE Chat, Glossary, TM, ...       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP REST / JSON (FastAPI)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                            BACKEND (FastAPI + Python 3.11+)                 │
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐  │
│  │   Translation Engine │  │   Documents Pipeline │  │  BrSE Intelligence│  │
│  │  - Context Builder   │  │  - DOCX/XLSX/PPTX/PDF│  │  - Meeting Analyzer│  │
│  │  - Hierarchical Gloss│  │  - RapidOCR (Images) │  │  - WorkItem Graph │  │
│  │  - TM Hybrid Search  │  │  - Token Protection  │  │  - Project Brain  │  │
│  │  - Ambiguity Detect  │  │  - Layout Preserving │  │  - Smart Reply Gen│  │
│  │  - QA Validator      │  │  - Segment Review    │  │  - Policy Engine  │  │
│  └──────────┬───────────┘  └──────────┬───────────┘  └─────────┬─────────┘  │
│             │                         │                        │            │
│  ┌──────────▼─────────────────────────▼────────────────────────▼──────────┐  │
│  │                       AI Provider Orchestration & Router              │  │
│  │     - Google Gemini API  │  Groq Cloud API  │  Ollama (Local Offline) │  │
│  │     - Auto Fallback Chain & Live Model Catalog Synchronization        │  │
│  └────────────────────────────────────┬───────────────────────────────────┘  │
│                                       │                                      │
│  ┌────────────────────────────────────▼───────────────────────────────────┐  │
│  │                      Data & Security Layer                             │  │
│  │     - SQLite (WAL Mode + FTS5 Full-Text Search)                        │  │
│  │     - SQLAlchemy 2.0 Async + AioSQLite                                 │  │
│  │     - AES-256 Fernet Encryption (API Keys, OAuth Tokens)               │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Cloud / OS Integration
┌──────────────────────────────────────▼──────────────────────────────────────┐
│  EXTERNAL SYSTEMS: Google Workspace (Drive, Docs, Sheets, Slides), Slack,   │
│                    LINE Messaging API, Windows Desktop Clipboard Agent       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2. Chi tiết Tech Stack
- **Backend:**
  - Ngôn ngữ & Framework: Python 3.11+, FastAPI (Async), Uvicorn.
  - Cơ sở dữ liệu: SQLite với WAL mode (Write-Ahead Logging), FTS5 (Full-Text Search), SQLAlchemy 2.0 (Async ORM), `aiosqlite`.
  - Bảo mật: `cryptography` (AES-256 Fernet) để mã hóa khóa API của AI Providers và OAuth Refresh Token của Google / Slack.
  - Xử lý tài liệu chuyên sâu: `python-docx` (Word), `openpyxl` (Excel), `python-pptx` (PowerPoint), `PyMuPDF` / `fitz` (PDF), `rapidocr_onnxruntime` + `Pillow` (OCR trích xuất chữ trong ảnh/sơ đồ).
  - Search & Vector: SQLite FTS5 (BM25 lexical search) + Vector Cosine Similarity (Embeddings từ Ollama `nomic-embed-text` hoặc model nhúng).
- **Frontend:**
  - Framework: React 19, TypeScript, Vite.
  - Styling: Tailwind CSS, Vanilla CSS animations.
  - Iconography: `lucide-react`.
  - HTTP Client: Axios có cấu hình interceptor cho local backend (`http://127.0.0.1:8000`).
- **AI Providers hỗ trợ:**
  - **Google Gemini:** `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash`...
  - **Groq Cloud:** `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` (tốc độ siêu nhanh, < 1-2s).
  - **Ollama (Offline/On-Premise):** `gemma4:12b`, `qwen2.5:14b`, `nomic-embed-text:latest` (chạy hoàn toàn cục bộ, bảo mật tuyệt đối).

---

## 3. CẤU TRÚC THƯ MỤC DỰ ÁN (PROJECT DIRECTORY TREE)

```text
AutomationTranslate/
├── apps/
│   ├── web/                         # Frontend React 19 + TypeScript + Vite
│   │   ├── src/
│   │   │   ├── api/                 # Axios clients & API definition modules
│   │   │   ├── components/          # Reusable UI components
│   │   │   │   ├── common/          # FileFormatIcon, badges, etc.
│   │   │   │   ├── integrations/    # GoogleDriveExplorer, GoogleAccountSwitcher, GoogleTranslateConfigModal
│   │   │   │   ├── modals/          # StakeholderManagerModal, QuickTranslateModal
│   │   │   │   ├── skeletons/       # Loading skeletons
│   │   │   │   ├── MarkdownView.tsx # Render markdown đẹp mắt
│   │   │   │   └── Sidebar.tsx      # Sidebar điều hướng 14+ tính năng
│   │   │   ├── context/             # ToastContext, ConfirmDialogContext
│   │   │   ├── pages/               # Các trang tính năng chính:
│   │   │   │   ├── TranslatorPage.tsx       # Màn hình dịch câu thông minh, đa ứng viên, QA, giải thích
│   │   │   │   ├── DocumentsPage.tsx        # Quản lý & dịch tài liệu DOCX, XLSX, PPTX, PDF, OCR ảnh
│   │   │   │   ├── IntegrationsPage.tsx     # Quản lý tích hợp Google Workspace, Slack, Desktop Agent
│   │   │   │   ├── BrSEDashboardPage.tsx    # Dashboard BrSE: Work items, Tasks, Bugs, Decisions
│   │   │   │   ├── MeetingsPage.tsx         # Xử lý biên bản họp: transcript, audio, action items, decisions
│   │   │   │   ├── ProjectBrainPage.tsx     # Hỏi đáp tri thức dự án (RAG), so sánh Diff & Impact Analysis
│   │   │   │   ├── LineSmartPage.tsx        # LINE Workspace: phân tích chat, sinh Smart Reply
│   │   │   │   ├── ProjectsPage.tsx         # Quản lý Project, quy tắc biên dịch (Rules)
│   │   │   │   ├── GlossaryPage.tsx         # Quản lý thuật ngữ đa tầng (Project/Client/Company/Global)
│   │   │   │   ├── MemoryPage.tsx           # Translation Memory (TM) tra cứu lai (Lexical + Vector)
│   │   │   │   ├── ProvidersPage.tsx        # Cấu hình API keys, kiểm tra kết nối, xếp ưu tiên AI
│   │   │   │   └── HistoryPage.tsx          # Lịch sử dịch, audit logs, xem chi tiết context
│   │   │   ├── types/               # Type definitions TypeScript
│   │   │   └── utils/               # AI Preferences, formatting helpers
│   │   ├── package.json
│   │   └── vite.config.ts
│   └── desktop/                     # Dự phòng mở rộng Electron/Tauri (hiện dùng Web + Local Agent)
├── data/                            # Thư mục chứa CSDL SQLite: comtor_copilot.db
├── sample_documents/                # Mẫu tài liệu test (.docx, .xlsx, .pptx, .pdf)
├── services/
│   └── backend/                     # Backend FastAPI Python
│       ├── app/
│       │   ├── api/                 # REST API Routers
│       │   │   ├── dashboard.py     # Endpoint thống kê dashboard
│       │   │   ├── documents.py     # Upload, dịch, download, preview segments tài liệu
│       │   │   ├── glossary.py      # CRUD Glossary thuật ngữ
│       │   │   ├── history.py       # Lịch sử dịch & sửa lỗi
│       │   │   ├── integrations/    # Router Google Workspace, Slack, Desktop Agent
│       │   │   ├── intelligence/    # Router BrSE Dashboard, Meetings, RAG, WorkItems, LINE, Stakeholders
│       │   │   ├── memory.py        # Quản lý Translation Memory
│       │   │   ├── projects.py      # Quản lý Dự án & Quy tắc dự án
│       │   │   ├── providers.py     # Quản lý AI Providers & đồng bộ live models
│       │   │   └── translate.py     # Endpoint dịch văn bản đơn lẻ, explain, generate reply
│       │   ├── core/                # Cấu hình hệ thống (Config, Database, Logging, Security)
│       │   ├── db/                  # SQLAlchemy Base, Models & Seed data
│       │   ├── documents/           # Xử lý tài liệu (Parsers, Renderers, OCR, Segmenter, QA)
│       │   │   ├── parsers/         # docx_parser, xlsx_parser, pptx_parser, pdf_parser
│       │   │   ├── renderers/       # docx_renderer, xlsx_renderer, pptx_renderer, pdf_renderer
│       │   │   ├── ocr/             # rapidocr engine, image_translator
│       │   │   ├── jobs.py          # Background Job Manager cho Document Translation
│       │   │   ├── qa.py            # QA cho tài liệu (bảo toàn số, url, placeholder)
│       │   │   └── segmenter.py     # Bộ chia đoạn & TokenProtector (bảo vệ code/tag)
│       │   ├── engine/              # Translation Engine cốt lõi
│       │   │   ├── context.py       # Context Engine (tập hợp rules, glossary, TM, corrections)
│       │   │   ├── pipeline.py      # Pipeline dịch 8 bước chuẩn Comtor
│       │   │   ├── prompt.py        # Modular Prompt Builder
│       │   │   ├── qa.py            # QA verification checker
│       │   │   └── router.py        # Phân tích độ phức tạp câu & điều phối model
│       │   ├── integrations/        # Kết nối dịch vụ bên ngoài
│       │   │   ├── google/          # Google Drive, Docs, Sheets, Slides AST Synchronizer & Job Manager
│       │   │   ├── slack/           # Slack Webhook / Bot Client, Thread analyzer
│       │   │   └── desktop/         # Desktop App Detector, Clipboard Listener
│       │   ├── intelligence/        # BrSE Intelligence Suite (Phase 4)
│       │   │   ├── extractors/      # Meeting, Requirement, Bug, Decision, TODO Analyzers
│       │   │   ├── brain/           # Ask Project Brain, Ask Meetings, Diff & Impact Analyzer
│       │   │   ├── rag/             # Document Chunker, SQLite FTS5 RAG Service
│       │   │   ├── reply/           # Advanced Smart Reply Engine (Kính ngữ + Commitment Safety)
│       │   │   ├── line/            # LINE Client & Webhook/Simulator handler
│       │   │   └── automation/      # Policy Engine (Tự động kích hoạt khi có event)
│       │   ├── providers/           # Adapter kết nối Gemini, Groq, Ollama
│       │   ├── schemas/             # Pydantic Schemas (Request / Response models)
│       │   └── main.py              # FastAPI app initialization, CORS, Lifespan Startup Tasks
│       ├── requirements.txt         # Danh sách thư viện Python
│       └── .env                     # File biến môi trường (Database path, API keys, URLs)
├── start.bat                        # Script khởi động 1-click cả Backend & Frontend
├── run.ps1                          # PowerShell Launcher
└── test.bat                         # Chạy bộ test tự động pytest
```

---

## 4. CÁC PHÂN HỆ NGHIỆP VỤ CỐT LÕI (CORE MODULES)

### 4.1. Phân hệ 1: Translation Engine & Comtor Context Pipeline
Quy trình dịch văn bản diễn ra theo 8 bước chặt chẽ:
1. **Language Detection:** Tự động nhận diện tiếng Nhật (`ja`), tiếng Việt (`vi`) hoặc tiếng Anh (`en`) dựa trên mật độ ký tự Kanji/Hiragana/Katakana vs ký tự tiếng Việt có dấu.
2. **Context Package Assembly:**
   - **Project Instructions:** Nạp các quy tắc dự án cụ thể (vd: "Giữ nguyên tên API", "Không dịch mã lỗi", "Xưng hô Tôi - Quý khách").
   - **Hierarchical Glossary Retrieval:** Thuật ngữ được truy xuất ưu tiên theo thứ bậc: `Project > Client > Company > Global`. Nếu trùng, thuật ngữ của Project sẽ ghi đè cấp cao hơn.
   - **Hybrid Translation Memory (TM):** Kết hợp tìm kiếm từ khóa khớp chính xác (Lexical substring) với so khớp ngữ nghĩa vector (Cosine similarity thông qua model nhúng).
   - **Continuous Correction Learning:** Nạp lại các bản sửa trước đó của con người (User Corrections) cho câu tương tự để AI không lặp lại lỗi cũ.
   - **Style Profile:** Định hình phong cách (Business, Polite, Very Polite, Natural, Technical, Casual).
3. **Task Complexity Analysis & Router:**
   - Phân tích câu: Đơn giản, Chứa thuật ngữ kỹ thuật, Chứa từ mơ hồ, Câu hội thoại, Câu giải thích.
   - Chọn model tối ưu theo thứ tự ưu tiên (ưu tiên model nhanh hoặc model mạnh tuỳ độ phức tạp).
4. **Modular Prompt Construction:** Đóng gói toàn bộ Context vào System Instruction và User Prompt theo định dạng JSON có cấu trúc.
5. **Provider Execution with Fallback:** Gọi API (Gemini / Groq / Ollama). Nếu provider chính gặp lỗi (hết quota, timeout, lỗi mạng), hệ thống tự động fallback tức thời sang provider dự phòng tiếp theo mà không làm gián đoạn người dùng.
6. **Ambiguity Detection & Multi-Candidate Generation:**
   - Khi phát hiện từ ngữ tiếng Nhật mơ hồ (đa nghĩa tùy ngữ cảnh như: `対象外`, `対応`, `検討`, `仕様`), AI trả về **2 đến 3 phương án dịch phân loại rõ ràng** (kèm lý do và ngữ cảnh ứng dụng) thay vì chỉ chọn bừa 1 kết quả.
7. **Automated QA Verification:**
   - Kiểm tra bảo toàn các con số (VD: số phiên bản, số tiền, ngày tháng).
   - Kiểm tra đường link URL, email.
   - Kiểm tra mã code, identifier (vd: `user_id`, `CamelCase`).
   - Kiểm tra việc tuân thủ các thuật ngữ bắt buộc từ Glossary.
8. **Audit Trail & Memory Persistence:** Lưu phiên dịch, độ trễ (latency_ms), cảnh báo QA, context đã dùng vào SQLite.

### 4.2. Phân hệ 2: Document Processing Engine (Tài liệu chuyên ngành)
Hỗ trợ dịch toàn diện các định dạng file tài liệu phổ biến nhất trong dự án IT:
- **Định dạng hỗ trợ:** Microsoft Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), Adobe PDF (`.pdf`), Ảnh chụp màn hình / Sơ đồ (`.png`, `.jpg`).
- **Cơ chế Token Protection (`TokenProtector`):**
  - Tự động phát hiện và bọc các thành phần nhạy cảm bằng token tạm thời (vd: `[[PROT_VAR_0]]`): Biến lập trình, URL, biểu thức chính quy, công thức tính toán.
  - Sau khi AI dịch xong, các token được khôi phục nguyên vẹn.
- **Bảo toàn công thức & cấu trúc bảng tính (Excel Parser/Renderer):**
  - Giữ nguyên toàn bộ công thức Excel (`SUM`, `VLOOKUP`, `IF`...).
  - Dịch tiêu đề cột, nội dung cell, comment/note mà không phá vỡ liên kết ô.
- **PDF Layout Preservation & Font Substitution (PyMuPDF):**
  - Trích xuất văn bản kèm tọa độ hình học (Bounding Boxes).
  - Tự động thay thế font chữ tiếng Nhật sang font hỗ trợ tiếng Việt Unicode không bị lỗi dấu font (như Roboto, Arial).
- **OCR Engine (RapidOCR ONNX Runtime):**
  - Xử lý ảnh chụp màn hình UI ứng dụng hoặc sơ đồ kiến trúc tiếng Nhật, trích xuất text và dịch đè lên vị trí tương ứng.
- **Side-by-side Segment Review Modal:**
  - Cho phép Comtor xem lại từng cặp câu gốc - câu dịch trước khi xuất bản thành file hoàn chỉnh.
  - Comtor có thể chỉnh sửa trực tiếp trên từng đoạn; bản sửa này tự động cập nhật vào Translation Memory.

### 4.3. Phân hệ 3: Cloud & OS Integrations
- **Google Workspace Integration (Drive, Docs, Sheets, Slides):**
  - Tích hợp chuẩn Google REST API qua OAuth 2.0 (mã hóa AES-256 token).
  - **Drive Explorer:** Duyệt thư mục Drive ngay trên giao diện Comtor Copilot.
  - **AST Synchronization:** Dịch trực tiếp trên Google Docs / Sheets / Slides giữ nguyên format hoặc xuất ra tài liệu mới có hậu tố `_VI`.
  - Hỗ trợ chế độ dịch **Song ngữ (Bilingual: gốc + dịch bên dưới)** hoặc **Thay thế (In-place replacement)**.
- **Slack Workspace Integration:**
  - Kết nối channel, giám sát tin nhắn.
  - Phân tích luồng tin nhắn (Thread), phát hiện yêu cầu khẩn cấp hoặc câu hỏi cần giải đáp.
- **Desktop Agent (Windows Integration):**
  - Tự động phát hiện ứng dụng đang hoạt động (Slack, Word, Excel, Teams).
  - Lắng nghe Clipboard để hỗ trợ dịch nhanh phím tắt (Quick Translate).

### 4.4. Phân hệ 4: BrSE Intelligence Suite & Project Brain
Phân hệ nâng cao dành riêng cho Kỹ sư cầu nối (Bridge Software Engineer):
1. **Meeting Minutes Analyzer (`MeetingAnalyzer`):**
   - Tiếp nhận bản ghi chép hoặc transcript cuộc họp (kể cả đầu ra từ Whisper/Voice STT).
   - **Xử lý hiện tượng lặp từ (Whisper Hallucination Cleaning):** Tự động loại bỏ các đoạn lặp lại vô nghĩa do AI nhận dạng giọng nói tạo ra.
   - **Map-Reduce Chunking:** Với các cuộc họp dài, hệ thống tự động bẻ nhỏ thành các session ~3,500 - 20,000 ký tự để không vượt ngưỡng Rate Limit (TPM) của AI Provider.
   - **Xuất bản báo cáo cuộc họp đa chiều:**
     + Tóm tắt song ngữ Nhật - Việt.
     + Danh sách Quyết định đã chốt (**Decisions**).
     + Danh sách Hành động cần làm (**Action Items / TODOs**) kèm người chịu trách nhiệm và deadline.
     + Các câu hỏi mở còn tồn đọng (**Open Questions**).
2. **Unified WorkItem & Evidence Graph:**
   - Quản trị toàn bộ thực thể dự án: `REQUIREMENT`, `BUG`, `QUESTION`, `DECISION`, `TODO`, `RISK`, `DEADLINE`.
   - **Nguyên tắc "Proof & Evidence":** Mọi mục AI trích xuất bắt buộc phải có câu trích dẫn nguyên văn (`quote_text`), người phát ngôn, thời điểm và nguồn gốc (Slack, LINE, Doc, Meeting).
   - **Conflict Detection:** Cảnh báo khi có mâu thuẫn giữa quyết định mới và yêu cầu cũ đã chốt.
3. **Project Brain & RAG (`ProjectRAGService`):**
   - Lập chỉ mục toàn bộ tài liệu dự án bằng SQLite FTS5 (BM25 full-text ranking).
   - **Ask Project / Ask Meetings:** BrSE có thể đặt câu hỏi tự nhiên bằng tiếng Việt hoặc tiếng Nhật về dự án (VD: "Quy tắc làm tròn số tiền tệ của khách hàng chốt ngày nào?", "Màn hình Đăng nhập xử lý khóa tài khoản sau mấy lần sai?").
   - AI tìm kiếm ngữ cảnh chính xác từ tài liệu, biên bản họp và trả lời kèm dẫn chứng xác thực.
4. **Smart Reply Generator (`AdvancedReplyEngine`):**
   - Sinh câu trả lời tiếng Nhật cho khách hàng theo 3 phong cách:
     1. Kính ngữ tiêu chuẩn (丁寧語 - Teineigo).
     2. Trang trọng đối ngoại (敬語 / 謙譲語 - Keigo/Kenjougo).
     3. Tạm hoãn an toàn (確認・回答保留 - Phản hồi đã tiếp nhận, sẽ kiểm tra với team).
   - **Quy tắc bảo vệ cam kết (Commitment Protection):** Nghiêm cấm AI tự ý hứa deadline hoặc tính năng nếu trong CSDL Quyết định chưa được duyệt.
5. **LINE Smart Workspace:**
   - Hỗ trợ làm việc với các khách hàng Nhật sử dụng LINE/LINE WORKS.
   - Tích hợp Webhook hoặc bộ giả lập Simulator, liên kết tin nhắn với Stakeholders và sinh câu phản hồi tại chỗ.

---

## 5. CƠ SỞ DỮ LIỆU & SCHEMA MODELS (SQLITE)

Dự án sử dụng SQLite (file đặt tại `data/comtor_copilot.db`), được chia thành các nhóm bảng chính:

### 5.1. Nhóm Quản lý Dự án & Cấu hình Cốt lõi
- **`projects`:** Thông tin dự án (`id`, `name`, `code`, `client_name`, `source_language`, `target_language`, `default_style`, `is_active`).
- **`project_instructions`:** Các quy tắc bắt buộc áp dụng khi dịch trong dự án (`project_id`, `rule_text`, `category`, `priority`).
- **`glossary_terms`:** Thuật ngữ dịch thuật (`source_term`, `target_term`, `scope`: `global`/`company`/`client`/`project`, `definition`, `category`, `priority`).
- **`translation_memory`:** Các phân đoạn câu đã dịch chuẩn (`source_text`, `target_text`, `quality_signal`, `embedding_vector`).
- **`translation_sessions` & `translation_results`:** Lưu vết lịch sử dịch, model AI đã dùng, độ trễ `latency_ms`, cảnh báo QA, các candidate translations dạng JSON.
- **`translation_corrections`:** Lưu lại các lần người dùng sửa câu dịch của AI để huấn luyện ngữ cảnh sau này.
- **`providers` & `routing_rules`:** Danh sách provider AI (`gemini`, `groq`, `ollama`), API key đã mã hóa, trạng thái health check và bảng định tuyến nhiệm vụ.

### 5.2. Nhóm Xử lý File Tài liệu (Documents)
- **`document_files`:** Quản lý file gốc upload lên (`filename`, `file_type`: docx/xlsx/pptx/pdf, `original_path`, `unit_count`).
- **`document_jobs`:** Tiến trình dịch tài liệu background (`status`: queued/analyzing/segmenting/translating/qa/rendering/completed/failed, `progress_percent`, `current_stage`, `output_path`).
- **`document_segments`:** Từng câu/đoạn trích xuất từ file (`location_json`: vị trí slide/sheet/page/cell, `source_text`, `translated_text`, `protected_tokens_json`, `status`).
- **`document_issues`:** Ghi nhận lỗi/cảnh báo layout, mất số, mất công thức (`severity`, `category`, `message`).

### 5.3. Nhóm Tích hợp Đám mây & Ứng dụng (Integrations)
- **`integration_accounts`:** Tài khoản kết nối Google Workspace, Slack (`provider`, `encrypted_access_token`, `encrypted_refresh_token`, `scopes_json`, `token_expiry`).
- **`google_folder_mappings` & `slack_channel_mappings`:** Ánh xạ thư mục Drive hoặc kênh Slack vào Project Workspace tương ứng.
- **`integration_caches`:** Bộ nhớ đệm thread chat và văn bản cloud (TTL 7 ngày).
- **`desktop_profiles`:** Ánh xạ phần mềm đang chạy trên Windows với chế độ dịch tương ứng.

### 5.4. Nhóm Trí tuệ BrSE & Tri thức Dự án (Intelligence)
- **`work_items`:** Các hạng mục nghiệp vụ (`item_type`: REQUIREMENT, BUG, QUESTION, DECISION, TODO, RISK; `status`: PROPOSED, CONFIRMED, DONE; `priority`, `assignee`, `deadline_date`).
- **`work_item_evidence`:** Minh chứng nguồn gốc của work item (`quote_text`, `source_type`: meeting/slack/line/docx, `author`, `confidence`).
- **`meeting_records`:** Biên bản họp (`meeting_date`, `participants_json`, `transcript_text`, `summary_markdown`, `decisions_json`, `action_items_json`, `open_questions_json`).
- **`project_document_chunks` & `fts_project_documents` (Virtual Table):** Các khối phân mảnh văn bản kèm chỉ mục tìm kiếm toàn văn FTS5 cho RAG.
- **`project_stakeholders`:** Danh bạ các nhân sự liên quan phía Khách hàng và Offshore (`name`, `role`, `organization`, `platform`).
- **`line_captured_messages`:** Tin nhắn từ LINE được ghi nhận kèm gợi ý Smart Reply và liên kết phân tích.
- **`automation_rules` & `automation_run_logs`:** Quản lý chính sách tự động hóa (Policy Automation) và nhật ký kích hoạt.

---

## 6. DANH MỤC API ENDPOINTS CHÍNH (REST API)

| Nhóm API | Method | Endpoint | Mô tả chức năng |
| :--- | :--- | :--- | :--- |
| **Translate** | `POST` | `/api/translate` | Dịch văn bản với Context Package, QA, Ambiguity detection |
| | `POST` | `/api/translate/explain` | Giải thích ngữ pháp tiếng Nhật & thuật ngữ IT trong câu |
| | `POST` | `/api/translate/reply` | Gợi ý 3 mẫu câu trả lời theo phong cách kính ngữ |
| **Documents** | `POST` | `/api/documents/upload` | Upload tài liệu (.docx, .xlsx, .pptx, .pdf, ảnh) |
| | `POST` | `/api/documents/translate` | Khởi tạo background job dịch tài liệu |
| | `GET` | `/api/documents/jobs/{job_id}/status` | Theo dõi tiến độ dịch tài liệu theo thời gian thực |
| | `GET` | `/api/documents/jobs/{job_id}/segments` | Lấy danh sách các cặp câu để review/chỉnh sửa |
| | `POST` | `/api/documents/segments/{seg_id}/edit` | Lưu sửa đổi câu dịch từ người dùng |
| | `GET` | `/api/documents/download/{job_id}` | Tải file tài liệu đã hoàn thành |
| **Integrations** | `GET` | `/api/integrations/google/drive/files` | Lấy danh sách file/folder từ Google Drive |
| | `POST` | `/api/integrations/google/jobs/start` | Bắt đầu dịch trực tiếp trên Google Docs/Sheets/Slides |
| | `GET` | `/api/integrations/google/jobs/{job_id}/status` | Trạng thái job dịch Google Workspace |
| | `POST` | `/api/integrations/google/sync-doc` | Đồng bộ nội dung AST xuống tài liệu Google |
| **Intelligence** | `POST` | `/api/intelligence/meetings/analyze` | Phân tích transcript cuộc họp (Minutes, Actions, Decisions) |
| | `POST` | `/api/intelligence/ask-project` | RAG hỏi đáp tri thức dự án qua FTS5 & evidence |
| | `POST` | `/api/intelligence/ask-meetings` | RAG hỏi đáp riêng trên biên bản các cuộc họp |
| | `POST` | `/api/intelligence/smart-reply` | Sinh câu trả lời chuẩn kính ngữ và an toàn cam kết |
| | `POST` | `/api/intelligence/diff` | So sánh khác biệt giữa 2 phiên bản đặc tả kỹ thuật |
| | `POST` | `/api/intelligence/impact` | Phân tích mức độ tác động khi thay đổi một module/hàm |
| | `GET` | `/api/intelligence/work-items` | Lấy danh sách Requirements, Bugs, Decisions dự án |
| **Providers** | `GET` | `/api/providers` | Lấy danh sách AI Providers và trạng thái health check |
| | `POST` | `/api/providers/refresh-models` | Quét live models mới nhất từ Google Gemini, Groq, Ollama |
| | `POST` | `/api/providers/test` | Kiểm tra kết nối và đo độ trễ mạng của API key |

---

## 7. CƠ CHẾ VẬN HÀNH & TRIỂN KHAI (QUICK START)

1. **Khởi động 1-Click (Khuyên dùng trên Windows):**
   - Click đúp vào file `start.bat` tại thư mục gốc.
   - Script tự động:
     - Kích hoạt Python virtual environment (`services/backend/.venv`).
     - Khởi động backend FastAPI tại `http://127.0.0.1:8000`.
     - Khởi động Vite React dev server tại `http://127.0.0.1:5173`.
     - Tự động mở trình duyệt web đến giao diện ứng dụng.
2. **Khởi chạy bằng PowerShell:**
   ```powershell
   .\run.ps1
   ```
3. **Chạy Unit Tests & DoD Scenarios:**
   ```bat
   test.bat
   ```

---

## 8. HƯỚNG DẪN PROMPT DÀNH CHO CHATGPT (SYSTEM PROMPT DÙNG TÀI LIỆU NÀY)

Khi bạn muốn ChatGPT hỗ trợ lập trình, debug hoặc mở rộng tính năng cho dự án này, hãy copy toàn bộ tài liệu này và gửi kèm prompt mở đầu như sau:

> *"Bạn là Kỹ sư phần mềm cao cấp am hiểu sâu sắc về kiến trúc ứng dụng Python FastAPI, React TypeScript và nghiệp vụ dịch thuật IT Nhật - Việt (Comtor/BrSE). Dưới đây là tài liệu kiến trúc tổng quan (Master Context) của dự án **AI Comtor / BrSE Copilot**. Hãy đọc kỹ context này để nắm rõ toàn bộ cấu trúc dự án, các models, luồng xử lý và công nghệ đang sử dụng. Sau khi đọc xong, hãy xác nhận bạn đã hiểu và sẵn sàng hỗ trợ tôi thực hiện các yêu cầu tiếp theo."*
