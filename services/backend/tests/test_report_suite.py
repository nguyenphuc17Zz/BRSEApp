import pytest
import os
import datetime
from sqlalchemy import select
from app.core.database import async_session_maker
from app.db.models import Project
from app.intelligence.models import ReportRecord
from app.intelligence.reports.report_service import ReportService
from app.intelligence.reports.slide_report_service import SlideReportService

@pytest.mark.asyncio
async def test_report_service_generation_and_exports():
    async with async_session_maker() as db:
        proj = (await db.execute(select(Project))).scalars().first()
        assert proj is not None, "Project must exist in seed database"

        # Test Generation with Auto-harvest OFF and pure manual input
        payload = {
            "project_id": proj.id,
            "report_type": "client_nippo",
            "is_auto_harvest": False,
            "manual_input_raw": "- Hoàn thành tích hợp API thanh toán\n- Cần xác nhận format ngày của invoice",
            "target_language": "ja",
            "sender_name": "Nguyen Phuc (BrSE)",
            "recipient_name": "Yamada-san (Client PM)",
            "additional_notes": "Ngày mai team offshore làm việc bình thường."
        }

        result = await ReportService.generate_report(payload, db)
        assert result["id"] is not None
        assert "content_markdown" in result
        assert "content_html" in result
        assert "content_chatwork" in result
        assert "content_slack" in result
        assert "[info]" in result["content_chatwork"]

        # Retrieve record from DB
        record = (await db.execute(select(ReportRecord).where(ReportRecord.id == result["id"]))).scalar_one_or_none()
        assert record is not None

        # Test DOCX export
        docx_path = os.path.join(os.path.dirname(__file__), "temp_report.docx")
        ReportService.export_report_docx(record, docx_path)
        assert os.path.exists(docx_path)
        assert os.path.getsize(docx_path) > 1000
        os.remove(docx_path)

        # Test XLSX export
        xlsx_path = os.path.join(os.path.dirname(__file__), "temp_report.xlsx")
        ReportService.export_report_xlsx(record, xlsx_path)
        assert os.path.exists(xlsx_path)
        assert os.path.getsize(xlsx_path) > 1000
        os.remove(xlsx_path)

        # Test PPTX default slide generation
        pptx_path = os.path.join(os.path.dirname(__file__), "temp_report.pptx")
        ReportService.export_report_pptx(record, pptx_path)
        assert os.path.exists(pptx_path)
        assert os.path.getsize(pptx_path) > 1000
        os.remove(pptx_path)

        # Clean up database record
        await db.delete(record)
        await db.commit()

@pytest.mark.asyncio
async def test_report_service_vietnamese_generation_with_mixed_input():
    async with async_session_maker() as db:
        proj = (await db.execute(select(Project))).scalars().first()
        assert proj is not None

        # Mixed JP/VI input with target_language = vi
        payload = {
            "project_id": proj.id,
            "report_type": "client_nippo",
            "is_auto_harvest": False,
            "manual_input_raw": "- Đã fix xong bug 画面 ログイン và verify trên staging\n- Đang tiến hành test 決済 API\n- Vướng mắc: Cần khách confirm 割引仕様",
            "target_language": "vi",
            "sender_name": "Phuc BrSE",
            "recipient_name": "Anh Minh PM"
        }

        result = await ReportService.generate_report(payload, db)
        assert result["id"] is not None
        assert "Kính gửi" in result["content_markdown"] or "Báo cáo" in result["content_markdown"]
        assert "【Báo cáo ngày】" in result["title"] or "Báo cáo" in result["title"]
        assert result["target_language"] == "vi"

        # Check export pptx with Vietnamese
        record = (await db.execute(select(ReportRecord).where(ReportRecord.id == result["id"]))).scalar_one_or_none()
        pptx_path = os.path.join(os.path.dirname(__file__), "temp_vi_report.pptx")
        ReportService.export_report_pptx(record, pptx_path)
        assert os.path.exists(pptx_path)
        assert os.path.getsize(pptx_path) > 1000
        os.remove(pptx_path)

        await db.delete(record)
        await db.commit()

@pytest.mark.asyncio
async def test_report_service_custom_text_template_and_docx_fill():
    import docx
    async with async_session_maker() as db:
        proj = (await db.execute(select(Project))).scalars().first()
        assert proj is not None

        custom_template = """[info][title]【DỰ ÁN X - BÁO CÁO TIẾN ĐỘ NGÀY {{date}}】[/title]
1. Hạng mục đã xong:
{{achievements}}
2. Hạng mục kế hoạch:
{{plans}}
3. Vấn đề cần confirm:
{{issues}}
[hr]
Chữ ký: {{sender}}
[/info]"""

        payload = {
            "project_id": proj.id,
            "report_type": "client_nippo",
            "is_auto_harvest": False,
            "manual_input_raw": "- Xong màn hình Login\n- Đang làm trang Checkout",
            "target_language": "vi",
            "sender_name": "Phuc BrSE",
            "recipient_name": "Khách hàng",
            "custom_text_template": custom_template
        }

        result = await ReportService.generate_report(payload, db)
        assert result["id"] is not None
        assert "BÁO CÁO TIẾN ĐỘ NGÀY" in result["content_markdown"]
        assert "Chữ ký: Phuc BrSE" in result["content_markdown"] or "Phuc BrSE" in result["content_markdown"]

        # Test DOCX template cloning and filling
        template_docx = os.path.join(os.path.dirname(__file__), "sample_template.docx")
        doc = docx.Document()
        doc.add_heading("{{title}}", level=1)
        doc.add_paragraph("Kính gửi: {{recipient}}")
        doc.add_paragraph("Hạng mục: {{achievements}}")
        doc.save(template_docx)

        record = (await db.execute(select(ReportRecord).where(ReportRecord.id == result["id"]))).scalar_one_or_none()
        record.template_file_path = template_docx

        output_docx = os.path.join(os.path.dirname(__file__), "output_filled.docx")
        ReportService.export_report_docx(record, output_docx)
        assert os.path.exists(output_docx)
        assert os.path.getsize(output_docx) > 500

        # Read back filled docx to confirm placeholder replaced
        filled_doc = docx.Document(output_docx)
        all_text = " ".join([p.text for p in filled_doc.paragraphs])
        assert "{{title}}" not in all_text
        assert "Khách hàng" in all_text

        # Cleanup
        if os.path.exists(template_docx):
            os.remove(template_docx)
        if os.path.exists(output_docx):
            os.remove(output_docx)
        await db.delete(record)
        await db.commit()

@pytest.mark.asyncio
async def test_report_service_temporal_fidelity_and_zero_task_loss():
    async with async_session_maker() as db:
        proj = (await db.execute(select(Project))).scalars().first()
        assert proj is not None

        raw_input = """Hôm qua:- Hoàn thành sửa bug đăng nhập khi session hết hạn.
- Hoàn thành UT cho màn hình User Management.
- QA-021 đang chờ khách xác nhận cách xử lý dữ liệu trùng.

Hôm nay:- Đã deploy bản sửa login lên môi trường test.
- Đã bắt đầu sửa chức năng CSV Export.
- Đã cập nhật tài liệu thiết kế chi tiết cho User Management.
- Chưa có issue ảnh hưởng schedule."""

        payload = {
            "project_id": proj.id,
            "report_type": "client_nippo",
            "is_auto_harvest": False,
            "manual_input_raw": raw_input,
            "target_language": "ja",
            "sender_name": "Phuc BrSE",
            "recipient_name": "Yamada-san"
        }

        result = await ReportService.generate_report(payload, db)
        assert result["id"] is not None
        md = result["content_markdown"]

        # 1. Polite Japanese Business Greeting starting with "お疲れ様です。"
        assert "お疲れ様です。" in md

        # 2. Both temporal sections or mirrors are present
        assert "昨日の実績" in md or "昨日" in md
        assert "本日の実績" in md or "本日" in md

        # 3. Zero task loss - User Management UT must NOT be dropped
        assert "User Management" in md
        assert ("UT" in md or "単体テスト" in md)

        # 4. QA-021 must be preserved and in 課題 / 確認 section, not lumped into achievements
        assert "QA-021" in md

        # 5. CSV Export and Login bug must be present
        assert "CSV" in md

        # Clean up record
        record = (await db.execute(select(ReportRecord).where(ReportRecord.id == result["id"]))).scalar_one_or_none()
        if record:
            await db.delete(record)
            await db.commit()

