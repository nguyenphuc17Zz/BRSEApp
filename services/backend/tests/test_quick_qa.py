import pytest
from sqlalchemy import select
from app.core.database import async_session_maker
from app.db.models import Project
from app.qa.models import TestCase, QAOpenQuestion
from app.intelligence.models import WorkItem
from app.qa.quick_qa_service import QuickQAService

@pytest.mark.asyncio
async def test_quick_qa_all_modes_and_save():
    async with async_session_maker() as db:
        proj = (await db.execute(select(Project))).scalars().first()
        assert proj is not None

        # 1. Test Case Polish Mode
        polish_res = await QuickQAService.analyze({
            "project_id": proj.id,
            "spec_text": "Test thử trường hợp user ấn nút thanh toán 2 lần liên tiếp thật nhanh xem có bị trừ tiền 2 lần ko",
            "mode": "test_case_polish",
            "is_auto_harvest": False
        }, db)
        assert polish_res is not None
        assert "title_ja" in polish_res or "purpose_ja" in polish_res
        assert len(polish_res.get("steps", [])) > 0

        # 2. Bug Draft Mode
        bug_res = await QuickQAService.analyze({
            "project_id": proj.id,
            "spec_text": "Khách báo bản prod bị văng lỗi khi import file CSV to. Log: OutOfMemoryError: Java heap space",
            "mode": "bug_draft",
            "is_auto_harvest": False
        }, db)
        assert bug_res is not None
        assert "client_reply_keigo" in bug_res
        assert "actual_behavior" in bug_res or "bug_title_ja" in bug_res

        # 3. Dev Inquiry Mode
        inquiry_res = await QuickQAService.analyze({
            "project_id": proj.id,
            "spec_text": "Nút Hủy đơn hàng, nếu đã giao bên vận chuyển thì có cho hủy ko? Bấm hủy thì hoàn tiền ngay hay chờ admin duyệt? Spec không thấy ghi gì.",
            "mode": "dev_inquiry",
            "is_auto_harvest": False
        }, db)
        assert inquiry_res is not None
        assert "proposal_a" in inquiry_res or "target_function" in inquiry_res or "inquiry_title_ja" in inquiry_res

        # 4. Spec Ambiguity Hunter Mode
        ambiguity_res = await QuickQAService.analyze({
            "project_id": proj.id,
            "spec_text": "エラー時は適宜メッセージを表示し、速やかに前画面に戻る。CSVインポート対象項目は氏名、住所、電話番号等とする。",
            "mode": "spec_ambiguity",
            "is_auto_harvest": False
        }, db)
        assert ambiguity_res is not None

        # 5. Japan Test Data Generator Mode
        data_res = await QuickQAService.analyze({
            "project_id": proj.id,
            "spec_text": "Form đăng ký thông tin cá nhân và địa chỉ tại Nhật Bản",
            "mode": "japan_test_data",
            "is_auto_harvest": False
        }, db)
        assert data_res is not None
        assert "valid_test_data" in data_res or "boundary_edge_cases" in data_res

        # 6. Quick Checklist Mode
        checklist_res = await QuickQAService.analyze({
            "project_id": proj.id,
            "spec_text": "Thêm nút Xuất file CSV báo cáo tháng và hiển thị ngày xác nhận trên danh sách đơn hàng",
            "mode": "quick_checklist",
            "is_auto_harvest": False
        }, db)
        assert checklist_res is not None
        assert "items" in checklist_res or "checklist_title" in checklist_res
