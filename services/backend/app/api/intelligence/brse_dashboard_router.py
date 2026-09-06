import json
import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.logging import logger
from app.intelligence.models import WorkItem, WorkItemEvidence, MeetingRecord
from app.db.models import Project
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

router = APIRouter(prefix="/api/brse-dashboard", tags=["BrSE Daily Dashboard"])

class SummaryGenerateRequest(BaseModel):
    project_id: Optional[str] = None
    summary_type: str = "morning" # morning, evening, weekly
    preferred_provider: Optional[str] = "groq"
    model: Optional[str] = None
    language: Optional[str] = "vi" # vi (mặc định cho Dev team), ja (cho Khách Nhật), bilingual

@router.get("/metrics")
async def get_dashboard_metrics(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Calculates live dashboard metrics synthesized directly from real WorkItem records."""
    effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None
    
    # 1. Fetch work items
    stmt_w = select(WorkItem)
    if effective_pid:
        stmt_w = stmt_w.where(WorkItem.project_id == effective_pid)
    items = (await db.execute(stmt_w)).scalars().all()

    urgent_count = 0
    open_questions_count = 0
    deadlines_count = 0
    completed_count = 0
    conflicts_count = 0
    proposed_reqs_count = 0
    unresolved_bugs_count = 0
    recent_decisions_count = 0

    for it in items:
        if it.priority in ["CRITICAL", "HIGH"] and it.status not in ["DONE", "REJECTED"]:
            urgent_count += 1
        if it.item_type in ["OPEN_QUESTION", "QUESTION"] and it.status not in ["DONE", "REJECTED"]:
            open_questions_count += 1
        if it.item_type == "DEADLINE" or (it.deadline_date and it.status not in ["DONE", "REJECTED"]):
            deadlines_count += 1
        if it.status == "DONE":
            completed_count += 1
        if it.is_conflict or it.status == "CONFLICT":
            conflicts_count += 1
        if it.item_type == "REQUIREMENT":
            proposed_reqs_count += 1
        if it.item_type == "BUG" and it.status not in ["DONE", "REJECTED"]:
            unresolved_bugs_count += 1
        if it.item_type == "DECISION":
            recent_decisions_count += 1

    return {
        "urgent_count": urgent_count,
        "open_questions_count": open_questions_count,
        "deadlines_count": deadlines_count,
        "completed_count": completed_count,
        "conflicts_count": conflicts_count,
        "proposed_requirements_count": proposed_reqs_count,
        "unresolved_bugs_count": unresolved_bugs_count,
        "recent_decisions_count": recent_decisions_count,
        "total_items": len(items)
    }

@router.get("/inbox")
async def get_work_inbox(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Retrieves all pending AI-extracted items and real meeting decisions for human review."""
    effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None

    # 1. Fetch meetings
    stmt_m = select(MeetingRecord)
    if effective_pid:
        stmt_m = stmt_m.where(MeetingRecord.project_id == effective_pid)
    stmt_m = stmt_m.order_by(desc(MeetingRecord.meeting_date))
    meetings = (await db.execute(stmt_m)).scalars().all()

    meetings_list = [{"id": m.id, "title": m.title, "date": m.meeting_date} for m in meetings]

    # 2. Fetch work items (all decisions, questions, tasks, bugs, requirements are unified in WorkItem)
    stmt_w = select(WorkItem).options(selectinload(WorkItem.evidence_items))
    if effective_pid:
        stmt_w = stmt_w.where(WorkItem.project_id == effective_pid)
    stmt_w = stmt_w.order_by(desc(WorkItem.created_at))
    items = (await db.execute(stmt_w)).scalars().all()

    requirements = []
    bugs = []
    questions = []
    decisions = []
    deadlines = []

    for item in items:
        evs = [
            {
                "source_type": e.source_type,
                "quote": e.quote_text,
                "author": e.author
            } for e in item.evidence_items
        ]
        
        m_id = None
        m_title = None
        m_date = None
        if item.evidence_items:
            for ev in item.evidence_items:
                if ev.source_type == "meeting":
                    for mt in meetings:
                        if mt.id == ev.source_id or mt.title in ev.quote_text:
                            m_id = mt.id
                            m_title = mt.title
                            m_date = mt.meeting_date
                            break

        # Determine primary source and author
        primary_source = "meeting" if m_id else "manual"
        primary_author = None
        if evs:
            primary_source = evs[0].get("source_type") or primary_source
            primary_author = evs[0].get("author")

        payload = {
            "id": item.id,
            "project_id": item.project_id,
            "type": item.item_type,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "priority": item.priority or "MEDIUM",
            "confidence": item.confidence,
            "is_conflict": item.is_conflict,
            "conflict_notes": item.conflict_notes,
            "deadline_date": item.deadline_date,
            "assignee": item.assignee or "Team BrSE/Dev",
            "source_type": primary_source,
            "author": primary_author,
            "meeting_id": m_id,
            "meeting_title": m_title,
            "meeting_date": m_date,
            "created_at": item.created_at.isoformat() if item.created_at else "",
            "evidence": evs
        }

        if item.item_type == "DECISION":
            decisions.append(payload)
        elif item.item_type in ["OPEN_QUESTION", "QUESTION"]:
            questions.append(payload)
        elif item.item_type == "REQUIREMENT":
            requirements.append(payload)
        elif item.item_type == "BUG":
            bugs.append(payload)
        elif item.item_type in ["DEADLINE", "TODO"]:
            deadlines.append(payload)
        else:
            t_lower = (item.title + " " + item.description).lower()
            if any(k in t_lower for k in ["màn hình", "nghiệp vụ", "quy định", "csv", "import", "format"]):
                requirements.append(payload)
            elif any(k in t_lower for k in ["lỗi", "bug", "sự cố", "thất bại", "không chạy"]):
                bugs.append(payload)
            elif any(k in t_lower for k in ["hỏi", "chờ confirm", "chưa rõ", "xác nhận"]):
                questions.append(payload)
            else:
                deadlines.append(payload)

    return {
        "total_pending": len(items),
        "meetings": meetings_list,
        "requirements": requirements,
        "bugs": bugs,
        "decisions": decisions,
        "questions": questions,
        "deadlines": deadlines
    }
def _generate_offline_fallback(
    summary_type: str,
    lang: str,
    date_label: str,
    urgent_tasks: list,
    recent_decisions: list,
    items_count: int
) -> str:
    """Tạo bản báo cáo tóm tắt chuẩn định dạng BrSE ngay cả khi không có kết nối AI Provider."""
    if lang == "ja":
        if summary_type == "morning":
            decs_str = "\n".join(recent_decisions[:4]) if recent_decisions else "- 前回のミーティングで合意された仕様・ルールを継続適用。"
            urg_str = "\n".join(urgent_tasks[:3]) if urgent_tasks else "- マスターデータ関連モジュールの実装を予定通り推進。"
            return f"""## 🌅 朝会サマリー・本日の進捗計画 — {date_label}

### 🎯 1. 本日の最優先事項・目標
- **進捗管理:** 最優先タスク（計 {len(urgent_tasks)} 件）の進捗確認および開発進捗のモニタリング。
- **タスク割り当て:** プロジェクト内 {items_count} 件の課題について、担当者および期日の明確化を徹底。

### 📋 2. 直近の合意・決定事項
{decs_str}

### ⚠️ 3. リスク及びお客様への確認待ち事項
- CSVインポート形式および外部連携API仕様に関して、日本側ご担当者様への最終確認を実施予定。

### ⏰ 4. 本日の完了予定とネクストアクション
{urg_str}
"""
        else: # evening
            decs_str = "\n".join(recent_decisions[:4]) if recent_decisions else "- 本日確認された仕様変更および重要合意事項のチーム展開完了。"
            urg_str = "\n".join(urgent_tasks[:3]) if urgent_tasks else "- 明日予定のモジュール実装およびテスト準備の完了。"
            return f"""## 🌆 日次進捗報告・夕会ラップアップ — {date_label}

### ✅ 1. 本日の対応完了事項
- **開発進捗:** 本日予定していたタスクの対応およびコードレビューを順調に完了。
- **課題管理:** プロジェクト全体の {items_count} 件の課題状況を最新化し、ブロッカーの有無を確認済み。

### 📋 2. 本日確定した技術仕様・決定事項
{decs_str}

### ⚠️ 3. 発生した課題・未解決のQA（確認事項）
- 外部システム連携に関する不明点について、質問票（Q&Aシート）を作成のうえ日本側へ共有準備中。

### 📅 4. 明日の作業予定及び直近のマイルストーン
{urg_str}
"""
    elif lang == "bilingual":
        if summary_type == "morning":
            decs_str = "\n".join(recent_decisions[:4]) if recent_decisions else "- Duy trì các quy định đã thống nhất / 前回の合意事項を継続。"
            urg_str = "\n".join(urgent_tasks[:3]) if urgent_tasks else "- Tiếp tục triển khai các module master data theo kế hoạch."
            return f"""## 🌅 Báo cáo Đầu ngày (Morning Briefing) / 朝会サマリー — {date_label}

### 🎯 1. Mục tiêu & Ưu tiên hàng đầu (本日の最優先事項)
- **Kiểm soát tiến độ (進捗管理):** Theo dõi {len(urgent_tasks)} hạng mục ưu tiên cao và các mốc bàn giao sắp tới (最優先課題 {len(urgent_tasks)} 件の進捗を管理)。
- **Phân công nhiệm vụ (タスク配分):** Đảm bảo toàn bộ {items_count} công việc trong dự án có đầu mối rõ ràng (全 {items_count} 件の課題の担当明確化)。

### 📋 2. Quyết định kỹ thuật đã thống nhất (合意された決定事項)
{decs_str}

### ⚠️ 3. Rủi ro & Vấn đề tồn đọng (リスク・確認待ち事項)
- Cần xác nhận lại với khách hàng về format CSV import và phương án hạ tầng máy chủ (CSV形式およびサーバ構成の確認要)。

### ⏰ 4. Hạn chót & Kế hoạch tiếp theo (期限とネクストアクション)
{urg_str}
"""
        else: # evening
            decs_str = "\n".join(recent_decisions[:4]) if recent_decisions else "- Đã cập nhật các quyết định trong ngày / 本日の決定事項を共有済み。"
            urg_str = "\n".join(urgent_tasks[:3]) if urgent_tasks else "- Kế hoạch ngày mai: Tiếp tục hoàn thiện các module master data."
            return f"""## 🌆 Báo cáo Tổng kết Cuối ngày (End-of-Day Wrap-up) / 日次進捗報告 — {date_label}

### ✅ 1. Tổng kết công việc đã hoàn thành trong ngày (本日の完了事項)
- **Tiến độ hôm nay (本日の進捗):** Đã hoàn tất các task dev theo kế hoạch và rà soát pull requests (本日のタスク対応およびPRレビューを完了)。
- **Quản lý tồn đọng (課題管理):** Cập nhật trạng thái {items_count} công việc, kiểm soát rủi ro phát sinh (全 {items_count} 件の進捗を最新化)。

### 📋 2. Quyết định kỹ thuật & Spec đã chốt trong ngày (本日確定した技術仕様)
{decs_str}

### ⚠️ 3. Khúc mắc phát sinh & Câu hỏi chờ phản hồi (発生した課題・未解決QA)
- Đang tổng hợp Q&A gửi khách hàng Nhật làm rõ format dữ liệu và quyền truy cập API (Q&Aシートにて日本側へ確認中)。

### 📅 4. Kế hoạch triển khai cho ngày mai (明日の作業予定)
{urg_str}
"""
    else: # default "vi" (100% Tiếng Việt cho Dev Team)
        if summary_type == "morning":
            decs_str = "\n".join(recent_decisions[:4]) if recent_decisions else "- Duy trì các quy định kỹ thuật đã thống nhất ở các cuộc họp trước."
            urg_str = "\n".join(urgent_tasks[:3]) if urgent_tasks else "- Tiếp tục triển khai các module chức năng theo sprint kế hoạch."
            return f"""## 🌅 Báo cáo Điều hành Đầu ngày (Morning Briefing) — {date_label}

### 🎯 1. Mục tiêu & Ưu tiên hàng đầu hôm nay
- **Kiểm soát tiến độ:** Theo dõi chặt chẽ {len(urgent_tasks)} hạng mục khẩn cấp / ưu tiên cao, tránh phát sinh trễ hạn.
- **Phân công nhiệm vụ:** Đảm bảo toàn bộ {items_count} công việc trong dự án có đầu mối xử lý và deadline cụ thể.

### 📋 2. Quyết định kỹ thuật & Spec đã chốt
{decs_str}

### ⚠️ 3. Rủi ro & Điểm cần làm rõ với khách hàng Nhật
- Khẩn trương tổng hợp Q&A gửi khách hàng về định dạng file import và logic kiểm tra hợp lệ.

### ⏰ 4. Hạn chót & Kế hoạch xử lý hôm nay
{urg_str}
"""
        else: # evening
            decs_str = "\n".join(recent_decisions[:4]) if recent_decisions else "- Cập nhật các quyết định kỹ thuật đã thống nhất vào tài liệu dự án."
            urg_str = "\n".join(urgent_tasks[:3]) if urgent_tasks else "- Chuẩn bị sẵn sàng cho kế hoạch làm việc ngày mai."
            return f"""## 🌆 Báo cáo Tổng kết Cuối ngày (End-of-Day Wrap-up) — {date_label}

### ✅ 1. Tổng kết công việc đã hoàn thành trong ngày
- **Tiến độ hôm nay:** Hoàn tất các công việc phát triển theo kế hoạch, rà soát pull requests.
- **Quản lý tồn đọng:** Cập nhật trạng thái {items_count} công việc, kiểm soát rủi ro phát sinh.

### 📋 2. Quyết định kỹ thuật & Spec đã chốt trong ngày
{decs_str}

### ⚠️ 3. Khúc mắc phát sinh & Câu hỏi chờ khách hàng phản hồi
- Đang tổng hợp Q&A gửi khách hàng Nhật làm rõ format dữ liệu và quyền truy cập API.

### 📅 4. Kế hoạch triển khai cho ngày mai & Hạn chót sắp tới
{urg_str}
"""

@router.post("/generate-summary")
async def generate_daily_summary(
    payload: SummaryGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Sinh báo cáo điều hành dự án (Morning Briefing hoặc Evening Wrap-up) theo chuẩn BrSE.
    Tự động tổng hợp dữ liệu từ WorkItem và MeetingRecord, sau đó yêu cầu AI soạn thảo.
    """
    effective_pid = payload.project_id if (payload.project_id and payload.project_id not in ("all", "default-project", "")) else None

    # Lấy danh sách cuộc họp
    stmt_m = select(MeetingRecord)
    if effective_pid:
        stmt_m = stmt_m.where(MeetingRecord.project_id == effective_pid)
    meetings = (await db.execute(stmt_m.order_by(desc(MeetingRecord.meeting_date)))).scalars().all()

    # Lấy danh sách work items
    stmt_w = select(WorkItem)
    if effective_pid:
        stmt_w = stmt_w.where(WorkItem.project_id == effective_pid)
    items = (await db.execute(stmt_w.order_by(desc(WorkItem.updated_at)))).scalars().all()

    # Categorize items directly from unified WorkItem records
    decisions = [i for i in items if i.item_type == "DECISION"]
    questions = [i for i in items if i.item_type in ["OPEN_QUESTION", "QUESTION"]]
    urgent_tasks_raw = [i for i in items if i.item_type in ["TODO", "DEADLINE"] and i.priority in ["CRITICAL", "HIGH"]]
    all_todos = [i for i in items if i.item_type in ["TODO", "DEADLINE"]]

    decisions_bullets = [f"- {d.title}: {d.description}" for d in decisions[:8]]
    recent_decisions = decisions_bullets
    questions_bullets = [f"- {q.title}" for q in questions[:6]]
    urgent_bullets = [f"- {t.title} (Hạn chót: {t.deadline_date or 'Ưu tiên hàng đầu'}, Phụ trách: {t.assignee or 'Đội ngũ kỹ thuật'})" for t in (urgent_tasks_raw if urgent_tasks_raw else all_todos[:6])]
    urgent_tasks = urgent_bullets
    general_tasks = [f"- {i.title}" for i in all_todos[:8]]

    date_label = datetime.date.today().strftime("%d/%m/%Y")
    lang = payload.language or "vi"

    # Xây dựng System Instruction và Prompt tùy biến chính xác theo ngôn ngữ mục tiêu
    if lang == "ja":
        system_instruction = (
            "あなたは日本のITプロジェクトで活躍する優秀なBrSE（ブリッジSE）リードです。"
            "日本側のクライアントやPMにそのままメールやチャットで報告・共有できるよう、"
            "丁寧かつ格調高いビジネス日本語（です・ます調、適切な敬語表現）のみで日次サマリーを作成してください。"
            "英語やベトナム語を混在させず、純粋なビジネス日本語で記述してください（一般的なIT専門用語を除く）。"
        )
        if payload.summary_type == "morning":
            summary_type_str = "朝会サマリー・本日の進捗計画 (Morning Briefing)"
            structure_str = """  1. 🎯 1. 本日の最優先事項・目標
  2. 📋 2. 直近の会議で合意された重要決定事項
  3. ⚠️ 3. リスク及びお客様への確認待ち事項
  4. ⏰ 4. 本日の完了予定とネクストアクション"""
        else:
            summary_type_str = "日次進捗報告・夕会ラップアップ (End-of-Day Wrap-up)"
            structure_str = """  1. ✅ 1. 本日の対応完了事項
  2. 📋 2. 本日確定した技術仕様・決定事項
  3. ⚠️ 3. 発生した課題・未解決のQA（確認事項）
  4. 📅 4. 明日の作業予定及び直近のマイルストーン"""

        prompt = f"""BrSEリードとして、本日（{date_label}）の【{summary_type_str}】を作成してください。

[プロジェクト実績データ]:
- 実施済み会議数: {len(meetings)} 回
- 直近の合意・決定事項:
{chr(10).join(decisions_bullets) if decisions_bullets else "- 直近で新規の決定事項はありません。"}

- リスク・確認待ちQA:
{chr(10).join(questions_bullets) if questions_bullets else "- 現在確認待ち事項はありません。"}

- 最優先・緊急対応タスク:
{chr(10).join(urgent_bullets) if urgent_bullets else "- 現在緊急課題はありません。"}

[作成要件]:
- 言語: 完全なビジネス日本語（丁寧語・敬語）。英語の混在を避け、日本の顧客がそのまま読める美しいMarkdown形式とすること。
- 構成:
{structure_str}
Markdown本文のみを出力し、挨拶文や前置き等の余計な解説は含めないでください。"""

    elif lang == "bilingual":
        system_instruction = (
            "Bạn là BrSE Lead (Kỹ sư cầu nối IT) cấp cao phụ trách điều phối dự án offshore Nhật Bản. "
            "Nhiệm vụ của bạn là tạo báo cáo điều hành song ngữ Nhật - Việt (JP/VI) chuẩn mực. "
            "Mỗi tiêu đề đề mục và mỗi gạch đầu dòng công việc phải có đầy đủ cả 2 ngôn ngữ: "
            "Tiếng Việt (dành cho Đội ngũ phát triển) và Tiếng Nhật Business Keigo (dành cho khách hàng Nhật). "
            "TUYỆT ĐỐI KHÔNG dùng tiếng Anh ngoại trừ các thuật ngữ kỹ thuật quốc tế chuẩn."
        )
        if payload.summary_type == "morning":
            summary_type_str = "BÁO CÁO ĐIỀU HÀNH ĐẦU NGÀY / 朝会サマリー (Morning Briefing)"
            structure_str = """  1. 🎯 1. Mục tiêu & Ưu tiên hàng đầu hôm nay / 本日の最優先事項
  2. 📋 2. Quyết định kỹ thuật đã thống nhất gần nhất / 直近の合意・決定事項
  3. ⚠️ 3. Rủi ro & Điểm cần làm rõ với khách hàng / リスク及び確認待ち事項
  4. ⏰ 4. Hạn chót & Kế hoạch hoàn thành hôm nay / 本日の期限とネクストアクション"""
        else:
            summary_type_str = "BÁO CÁO TỔNG KẾT CUỐI NGÀY / 日次進捗報告 (End-of-Day Wrap-up)"
            structure_str = """  1. ✅ 1. Tổng kết công việc đã hoàn thành trong ngày / 本日の完了事項
  2. 📋 2. Quyết định kỹ thuật & Spec đã chốt trong ngày / 本日確定した技術仕様
  3. ⚠️ 3. Khúc mắc phát sinh & Câu hỏi chờ phản hồi / 発生した課題・未解決QA
  4. 📅 4. Kế hoạch triển khai ngày mai & Hạn chót / 明日の作業予定とマイルストーン"""

        prompt = f"""Bạn là BrSE Lead. Hãy viết bản {summary_type_str} cho ngày hôm nay ({date_label}).

[DỮ LIỆU THỰC TẾ DỰ ÁN]:
- Số cuộc họp đã thực hiện: {len(meetings)} cuộc họp
- Các quyết định quan trọng chốt gần nhất:
{chr(10).join(decisions_bullets) if decisions_bullets else "- Chưa ghi nhận quyết định mới."}

- Các vấn đề cần làm rõ / Câu hỏi mở:
{chr(10).join(questions_bullets) if questions_bullets else "- Không có câu hỏi mở."}

- Các công việc khẩn cấp / ưu tiên cao:
{chr(10).join(urgent_bullets) if urgent_bullets else "- Không có việc khẩn cấp."}

[YÊU CẦU ĐỊNH DẠNG]:
- Ngôn ngữ: Song ngữ Nhật - Việt chuẩn BrSE. Mỗi ý có cả tiếng Việt và tiếng Nhật tương ứng. TUYỆT ĐỐI KHÔNG dùng tiếng Anh.
- Cấu trúc:
{structure_str}
Chỉ trả về nội dung Markdown, không kèm lời giải thích râu ria."""

    else: # Mặc định "vi": 100% Tiếng Việt cho Dev Team
        system_instruction = (
            "Bạn là BrSE Lead (Kỹ sư cầu nối IT) cấp cao phụ trách điều phối dự án offshore Nhật Bản. "
            "Nhiệm vụ của bạn là tổng hợp báo cáo điều hành chuyên nghiệp bằng 100% TIẾNG VIỆT tự nhiên, rành mạch, súc tích dành cho Dev Team Việt Nam. "
            "TUYỆT ĐỐI KHÔNG sử dụng tiếng Anh cho câu văn, đề mục hoặc giải thích (ngoại trừ các thuật ngữ kỹ thuật quốc tế không thể dịch như API, OAuth2, Token, Job queue, CSV)."
        )
        if payload.summary_type == "morning":
            summary_type_str = "BÁO CÁO ĐIỀU HÀNH ĐẦU NGÀY (Morning Briefing)"
            structure_str = """  1. 🎯 1. Mục tiêu & Ưu tiên hàng đầu hôm nay
  2. 📋 2. Quyết định kỹ thuật đã thống nhất gần nhất
  3. ⚠️ 3. Rủi ro & Điểm cần làm rõ với khách hàng Nhật
  4. ⏰ 4. Hạn chót & Kế hoạch xử lý hôm nay"""
        else:
            summary_type_str = "BÁO CÁO TỔNG KẾT CUỐI NGÀY (End-of-Day Wrap-up)"
            structure_str = """  1. ✅ 1. Tổng kết công việc đã hoàn thành trong ngày
  2. 📋 2. Quyết định kỹ thuật & Spec đã chốt trong ngày
  3. ⚠️ 3. Khúc mắc phát sinh & Câu hỏi chờ khách hàng phản hồi
  4. 📅 4. Kế hoạch triển khai cho ngày mai & Hạn chót sắp tới"""

        prompt = f"""Bạn là BrSE Lead. Hãy viết bản {summary_type_str} cho ngày hôm nay ({date_label}) dành cho Dev Team Việt Nam.

[DỮ LIỆU THỰC TẾ DỰ ÁN]:
- Số cuộc họp đã thực hiện: {len(meetings)} cuộc họp
- Các quyết định quan trọng chốt gần nhất:
{chr(10).join(recent_decisions[:6]) if recent_decisions else "- Chưa ghi nhận quyết định mới."}

- Các công việc khẩn cấp / ưu tiên cao:
{chr(10).join(urgent_tasks) if urgent_tasks else "- Không có việc khẩn cấp."}

- Các công việc đang thực hiện:
{chr(10).join(general_tasks)}

[YÊU CẦU ĐỊNH DẠNG]:
- Ngôn ngữ: 100% TIẾNG VIỆT chuẩn IT công sở. TUYỆT ĐỐI KHÔNG DÙNG TIẾNG ANH (ngoại trừ tên thuật ngữ kỹ thuật không thể dịch).
- Cấu trúc:
{structure_str}
Chỉ trả về nội dung Markdown, không kèm lời giải thích râu ria."""

    prov_name = payload.preferred_provider or "groq"
    provider_chain = [prov_name, "gemini", "groq"] if prov_name not in ["auto", None] else ["groq", "gemini"]

    generated_md = None
    used_prov = "system"

    for prov_c in provider_chain:
        p = provider_registry.get_provider(prov_c)
        if not p:
            continue
        try:
            t_model = payload.model if (prov_c == prov_name and payload.model) else None
            resp = await p.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                model=t_model,
                temperature=0.2,
                json_mode=False,
                max_tokens=2048
            )
            if resp and resp.text and len(resp.text.strip()) > 80:
                raw_text = resp.text.strip()
                try:
                    parsed_json = clean_json_response(raw_text)
                    if isinstance(parsed_json, dict):
                        for k in ["markdown", "content", "summary", "briefing", "text"]:
                            if parsed_json.get(k):
                                raw_text = parsed_json[k]
                                break
                except Exception:
                    pass
                generated_md = raw_text
                used_prov = prov_c
                break
        except Exception as e:
            logger.warning(f"Failed generating daily summary with {prov_c}: {e}")

    if not generated_md:
        generated_md = _generate_offline_fallback(
            summary_type=payload.summary_type,
            lang=lang,
            date_label=date_label,
            urgent_tasks=urgent_tasks,
            recent_decisions=recent_decisions,
            items_count=len(items)
        )

    return {
        "summary_type": payload.summary_type,
        "date": date_label,
        "markdown": generated_md,
        "provider": used_prov,
        "stats": {
            "total_meetings": len(meetings),
            "total_decisions": len(recent_decisions),
            "total_work_items": len(items),
            "urgent_items": len(urgent_tasks)
        }
    }
