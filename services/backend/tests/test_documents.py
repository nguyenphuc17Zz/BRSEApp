import pytest
from pathlib import Path
import docx
import openpyxl
from pptx import Presentation
from pptx.util import Inches
import pymupdf as fitz

from app.core.database import async_session_maker, init_db
from app.documents.segmenter import TokenProtector
from app.documents.parsers.docx_parser import DocxParser
from app.documents.parsers.xlsx_parser import XlsxParser
from app.documents.parsers.pptx_parser import PptxParser
from app.documents.parsers.pdf_parser import PdfParser
from app.documents.renderers.docx_renderer import DocxRenderer
from app.documents.renderers.xlsx_renderer import XlsxRenderer
from app.documents.renderers.pptx_renderer import PptxRenderer
from app.documents.qa import DocumentQAChecker
from app.documents.models import DocumentFile, DocumentJob, DocumentSegment
from app.documents.jobs import job_manager

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()

def test_token_protector():
    """Verify URLs, emails, ticket IDs, camelCase code identifiers are protected and restored."""
    text = "API endpoint https://api.bank.com/v1/auth requires userAdmin and ticket JIRA-1049."
    
    protected_text, mapping = TokenProtector.protect_tokens(text)
    assert "__PROTECTED_" in protected_text
    assert "https://api.bank.com/v1/auth" not in protected_text
    assert len(mapping) >= 2

    # Simulate AI translation keeping protected tokens
    translated_with_tokens = protected_text.replace("requires", "yêu cầu")
    restored, missing = TokenProtector.restore_tokens(translated_with_tokens, mapping)
    
    assert "https://api.bank.com/v1/auth" in restored
    assert len(missing) == 0
    assert "__PROTECTED_" not in restored

def test_docx_parser_and_renderer(tmp_path: Path):
    """Verify DOCX paragraphs, formatting runs, and tables are parsed and rendered preserving structure."""
    docx_file = tmp_path / "test_spec.docx"
    doc = docx.Document()
    doc.add_heading("仕様書 (Specification)", level=1)
    p = doc.add_paragraph()
    p.add_run("ユーザーはシステムに")
    run_bold = p.add_run("ログイン")
    run_bold.bold = True
    p.add_run("できます。")

    # Add table
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "項目 (Item)"
    table.cell(0, 1).text = "説明 (Description)"
    table.cell(1, 0).text = "パスワード"
    table.cell(1, 1).text = "8文字以上"
    doc.save(str(docx_file))

    # Parse
    parser = DocxParser()
    segments, metadata = parser.parse(docx_file)
    assert len(segments) >= 4
    assert metadata["paragraph_count"] >= 2
    assert metadata["table_count"] == 1

    # Build translations map using location keys
    segments_by_loc = {}
    for seg in segments:
        loc = seg.location
        if loc.get("type") == "paragraph":
            key = f"paragraph_{loc.get('p_index')}"
        elif loc.get("type") == "table_cell":
            key = f"table_cell_{loc.get('t_index')}_{loc.get('r_index')}_{loc.get('c_index')}"
        segments_by_loc[key] = f"[VI] {seg.source_text}"

    # Render
    output_file = tmp_path / "output_spec.docx"
    DocxRenderer.render(docx_file, output_file, segments_by_loc)
    assert output_file.exists()

    # Re-open and verify output
    out_doc = docx.Document(str(output_file))
    assert len(out_doc.paragraphs) >= 2
    assert len(out_doc.tables) == 1
    assert "[VI]" in out_doc.tables[0].cell(1, 0).text

@pytest.mark.asyncio
async def test_xlsx_parser_and_formula_protection(tmp_path: Path):
    """Verify Excel formula cells (=VLOOKUP, =SUM) are NEVER translated and strictly preserved."""
    xlsx_file = tmp_path / "test_project.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Requirements"

    ws["A1"] = "ユーザー名"
    ws["B1"] = "権限"
    ws["C1"] = 100
    ws["D1"] = "=VLOOKUP(A2,Sheet2!A:B,2,FALSE)"
    ws["E1"] = "=SUM(C1:C10)"
    ws["F1"] = "https://bank.com/api"

    wb.save(str(xlsx_file))

    # Parse
    parser = XlsxParser()
    segments, metadata = parser.parse(xlsx_file)

    # Formulas must NOT be extracted as translatable segments
    source_texts = [s.source_text for s in segments]
    assert "ユーザー名" in source_texts
    assert "権限" in source_texts
    assert "=VLOOKUP(A2,Sheet2!A:B,2,FALSE)" not in source_texts
    assert "=SUM(C1:C10)" not in source_texts

    # Render translated copy
    segments_by_loc = {}
    for s in segments:
        loc = s.location
        key = f"excel_cell_{loc['sheet']}_{loc['row']}_{loc['column']}"
        segments_by_loc[key] = f"Dịch: {s.source_text}"

    output_file = tmp_path / "output_project.xlsx"
    await XlsxRenderer.render(xlsx_file, output_file, segments_by_loc)
    assert output_file.exists()

    # Verify formulas remain 100% intact in rendered workbook
    out_wb = openpyxl.load_workbook(str(output_file), data_only=False)
    out_ws = out_wb["Requirements"]
    assert out_ws["A1"].value.startswith("Dịch:")
    assert out_ws["D1"].value == "=VLOOKUP(A2,Sheet2!A:B,2,FALSE)"
    assert out_ws["E1"].value == "=SUM(C1:C10)"

@pytest.mark.asyncio
async def test_pptx_parser_and_renderer(tmp_path: Path):
    """Verify PowerPoint slides, titles, body text boxes, and speaker notes are parsed and rendered."""
    pptx_file = tmp_path / "test_pres.pptx"
    prs = Presentation()
    blank_slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_slide_layout)

    # Add title & body
    txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = "システム概要"

    # Add speaker note
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = "このスライドでは全体の構成を説明します。"

    prs.save(str(pptx_file))

    # Parse
    parser = PptxParser()
    segments, metadata = parser.parse(pptx_file)
    assert len(segments) >= 2
    assert any("システム概要" in s.source_text for s in segments)
    assert any("全体の構成" in s.source_text for s in segments)

    # Render
    segments_by_loc = {}
    for s in segments:
        loc = s.location
        loc_type = loc.get("type")
        if loc_type == "pptx_shape_text":
            key = f"pptx_shape_text_{loc['slide_index']}_{loc['shape_index']}_{loc['paragraph_index']}"
        elif loc_type == "pptx_speaker_notes":
            key = f"pptx_speaker_notes_{loc['slide_index']}_{loc['paragraph_index']}"
        segments_by_loc[key] = f"VI: {s.source_text}"

    output_file = tmp_path / "output_pres.pptx"
    await PptxRenderer.render(pptx_file, output_file, segments_by_loc)
    assert output_file.exists()

    # Reopen to verify
    out_prs = Presentation(str(output_file))
    assert len(out_prs.slides) == 1
    assert "VI:" in out_prs.slides[0].notes_slide.notes_text_frame.text

def test_pdf_parser_native_text(tmp_path: Path):
    """Verify PyMuPDF extracts native text blocks with bounding boxes."""
    pdf_file = tmp_path / "test_doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "認証方式の概要 (Authentication Overview)", fontsize=14)
    page.insert_text((50, 120), "本システムはOAuth 2.0を使用します。", fontsize=11)
    doc.save(str(pdf_file))
    doc.close()

    # Parse
    parser = PdfParser()
    segments, metadata = parser.parse(pdf_file)
    assert len(segments) >= 2
    assert metadata["page_count"] >= 1
    assert metadata["total_segments"] >= 2
    assert segments[0].formatting_meta.get("bbox") is not None

def test_document_qa_checker():
    """Verify QA checker catches unrestored protected tokens and number mismatches."""
    # Missing token test
    source = "アクセス先: __PROTECTED_URL_1__"
    bad_target = "Địa chỉ truy cập: __PROTECTED_URL_1__ (chưa khôi phục)"
    mapping = {"__PROTECTED_URL_1__": "https://example.com"}

    issues = DocumentQAChecker.check_segment(
        job_id="job_test",
        segment_id="seg1",
        source_text=source,
        translated_text=bad_target,
        location_text="p1",
        protected_tokens_map=mapping
    )
    assert any(i.category == "token_unrestored" for i in issues)

    # Number mismatch test
    num_source = "合計 42 件のエラーが発生しました。"
    num_bad_target = "Có tổng cộng 99 lỗi phát sinh."
    num_issues = DocumentQAChecker.check_segment(
        job_id="job_test",
        segment_id="seg2",
        source_text=num_source,
        translated_text=num_bad_target,
        location_text="p2",
        protected_tokens_map={}
    )
    assert any(i.category == "number_mismatch" for i in num_issues)

@pytest.mark.asyncio
async def test_document_job_workflow_and_segment_editing(tmp_path: Path):
    """Verify document job lifecycle: segment persistence, manual editing, and output rendering."""
    # Create test DOCX
    docx_file = tmp_path / "lifecycle_test.docx"
    doc = docx.Document()
    doc.add_heading("仕様書", level=1)
    doc.add_paragraph("システム管理者はパスワードを変更できます。")
    doc.save(str(docx_file))

    async with async_session_maker() as db:
        doc_record = DocumentFile(
            filename="lifecycle_test.docx",
            file_type="docx",
            file_size=1024,
            original_path=str(docx_file),
            detected_language="ja",
            unit_count=2,
            unit_label="elements"
        )
        db.add(doc_record)
        await db.commit()
        await db.refresh(doc_record)

        job_record = DocumentJob(
            document_id=doc_record.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-2.5-flash",
            style="Polite"
        )
        db.add(job_record)
        await db.commit()
        await db.refresh(job_record)

        # Parse and populate segments
        parser = DocxParser()
        parsed_segs, _ = parser.parse(docx_file)
        
        db_segs = []
        import json
        for ps in parsed_segs:
            s = DocumentSegment(
                job_id=job_record.id,
                segment_index=ps.segment_index,
                location_json=json.dumps(ps.location),
                source_text=ps.source_text,
                protected_tokens_json=json.dumps(ps.protected_tokens),
                context_hint=ps.context_hint,
                status="pending"
            )
            db.add(s)
            db_segs.append(s)
        await db.commit()

        # Simulate translation of segments
        for s in db_segs:
            s.translated_text = f"Bản dịch tiếng Việt cho: {s.source_text}"
            s.status = "translated"
        await db.commit()

        # Test manual segment edit (User review screen)
        target_seg = db_segs[0]
        target_seg.translated_text = "Bản dịch đã được người dùng chỉnh sửa thủ công."
        target_seg.status = "user_edited"
        await db.commit()

        # Render output document
        output_file = tmp_path / "lifecycle_output.docx"
        await job_manager._render_output_document(
            file_type="docx",
            working_copy=docx_file,
            output_path=output_file,
            segments=db_segs
        )

        assert output_file.exists()
        out_doc = docx.Document(str(output_file))
        assert any("Bản dịch đã được người dùng chỉnh sửa thủ công." in p.text for p in out_doc.paragraphs)


def test_custom_output_filename(tmp_path: Path):
    from app.documents.storage import document_storage
    # 1. Custom filename with extension
    p1 = document_storage.get_output_path(
        original_filename="BaoCao.docx",
        target_lang="vi",
        custom_dir=str(tmp_path),
        custom_filename="BaoCao_Dich_TuyChinh.docx"
    )
    assert p1.name == "BaoCao_Dich_TuyChinh.docx"

    # 2. Custom filename without extension - automatically appends original extension
    p2 = document_storage.get_output_path(
        original_filename="BaoCao.docx",
        target_lang="vi",
        custom_dir=str(tmp_path),
        custom_filename="BaoCao_KhongDuoi"
    )
    assert p2.name == "BaoCao_KhongDuoi.docx"

    # 3. Collision handling: if file exists, appends counter
    p1.write_text("dummy")
    p3 = document_storage.get_output_path(
        original_filename="BaoCao.docx",
        target_lang="vi",
        custom_dir=str(tmp_path),
        custom_filename="BaoCao_Dich_TuyChinh.docx"
    )
    assert p3.name == "BaoCao_Dich_TuyChinh_1.docx"

    # 4. Default fallback when no custom filename
    p4 = document_storage.get_output_path(
        original_filename="BaoCao.docx",
        target_lang="vi",
        custom_dir=str(tmp_path),
        custom_filename=None
    )
    assert p4.name == "BaoCao_vi.docx"


