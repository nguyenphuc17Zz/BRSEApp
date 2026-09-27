import pytest
from pathlib import Path
import fitz
import docx
from docx.shared import Pt as DocxPt, RGBColor as DocxRGB
import openpyxl
from openpyxl.styles import Font as XlsxFont, PatternFill, Alignment as XlsxAlignment
import pptx
from pptx.util import Inches, Pt as PptxPt
from pptx.dml.color import RGBColor as PptxRGB

from app.documents.parsers.pdf_parser import PdfParser
from app.documents.renderers.pdf_renderer import PdfRenderer
from app.documents.parsers.docx_parser import DocxParser
from app.documents.renderers.docx_renderer import DocxRenderer
from app.documents.parsers.xlsx_parser import XlsxParser
from app.documents.renderers.xlsx_renderer import XlsxRenderer
from app.documents.parsers.pptx_parser import PptxParser
from app.documents.renderers.pptx_renderer import PptxRenderer


@pytest.mark.asyncio
async def test_pdf_typography_and_color_preservation(tmp_path):
    pdf_path = tmp_path / "styled_source.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Draw a colored background box (e.g., table header)
    bg_rect = fitz.Rect(50, 50, 400, 100)
    page.draw_rect(bg_rect, color=(0.1, 0.3, 0.6), fill=(0.1, 0.3, 0.6))

    # Insert text inside the box (white text, 16pt, bold)
    font_file = "C:/Windows/Fonts/msgothic.ttc"
    page.insert_textbox(
        fitz.Rect(55, 55, 395, 95),
        "重要なお知らせ",
        fontfile=font_file,
        fontname="msgothic",
        fontsize=16,
        color=(1.0, 1.0, 1.0)
    )

    # Insert secondary colored text (red, 12pt)
    page.insert_textbox(
        fitz.Rect(50, 120, 400, 150),
        "注意：この内容は機密情報です。",
        fontfile=font_file,
        fontname="msgothic",
        fontsize=12,
        color=(0.85, 0.1, 0.1)
    )
    doc.save(str(pdf_path))
    doc.close()

    # 1. Parse PDF and verify extracted typography metadata
    parser = PdfParser()
    segments, metadata = parser.parse(pdf_path)
    assert len(segments) >= 2

    # Check header segment
    hdr_seg = next(s for s in segments if "重要なお知らせ" in s.source_text)
    hdr_loc = hdr_seg.location
    assert hdr_loc.get("font_size") is not None
    assert hdr_loc["font_size"] >= 14.0
    assert hdr_loc.get("font_color") is not None
    assert len(hdr_loc["font_color"]) == 3
    # Check sampled background color is close to blue box (0.1, 0.3, 0.6)
    bg = hdr_loc.get("bg_color")
    assert bg is not None and len(bg) == 3

    # Check note segment
    note_seg = next(s for s in segments if "注意" in s.source_text)
    assert note_seg.location.get("font_size") is not None
    assert note_seg.location.get("font_color") is not None

    # 2. Render translated PDF
    output_pdf = tmp_path / "styled_translated.pdf"
    segments_by_loc = {
        f"pdf_text_block_{hdr_loc['page_index']}_{hdr_loc['block_no']}": "Thông báo quan trọng",
        f"pdf_text_block_{note_seg.location['page_index']}_{note_seg.location['block_no']}": "Lưu ý: Nội dung này là tài liệu mật."
    }
    raw_segments = [
        {"location": hdr_loc, "text": segments_by_loc[f"pdf_text_block_{hdr_loc['page_index']}_{hdr_loc['block_no']}"]},
        {"location": note_seg.location, "text": segments_by_loc[f"pdf_text_block_{note_seg.location['page_index']}_{note_seg.location['block_no']}"]}
    ]

    await PdfRenderer.render(
        working_path=pdf_path,
        output_path=output_pdf,
        segments_by_loc=segments_by_loc,
        raw_segments=raw_segments,
        options={"translate_images": False},
        tgt_lang="vi"
    )

    assert output_pdf.exists()
    out_doc = fitz.open(str(output_pdf))
    assert len(out_doc) == 1
    page_text = out_doc[0].get_text().replace('\xa0', ' ')
    assert "Thông báo quan trọng" in page_text
    assert "Lưu ý" in page_text
    out_doc.close()


def test_docx_style_and_header_footer_preservation(tmp_path):
    docx_path = tmp_path / "source.docx"
    doc = docx.Document()

    # Add header
    section = doc.sections[0]
    header_p = section.header.paragraphs[0]
    header_p.text = "社外秘 - プロジェクト仕様書"

    # Add paragraph with styled run
    p = doc.add_paragraph()
    r1 = p.add_run("第1章：システム構成")
    r1.bold = True
    r1.font.size = DocxPt(14)
    r1.font.color.rgb = DocxRGB(0x1F, 0x49, 0x7D)

    # Add table with styled cell
    table = doc.add_table(rows=2, cols=2)
    hdr_cell = table.rows[0].cells[0]
    hdr_cell_p = hdr_cell.paragraphs[0]
    hdr_run = hdr_cell_p.add_run("機能名称")
    hdr_run.bold = True
    hdr_run.font.size = DocxPt(11)

    data_cell = table.rows[1].cells[0]
    data_run = data_cell.paragraphs[0].add_run("ユーザー認証")

    # Add footer
    footer_p = section.footer.paragraphs[0]
    footer_p.text = "ページ 1 / 10"

    doc.save(str(docx_path))

    # 1. Parse DOCX
    parser = DocxParser()
    segments, meta = parser.parse(docx_path)
    assert any("社外秘" in s.source_text for s in segments)
    assert any("第1章" in s.source_text for s in segments)
    assert any("機能名称" in s.source_text for s in segments)
    assert any("ページ" in s.source_text for s in segments)

    # 2. Render DOCX
    output_docx = tmp_path / "translated.docx"
    segments_by_loc = {
        "docx_header_0_0": "MẬT - Tài liệu đặc tả dự án",
        "paragraph_0": "Chương 1: Cấu trúc hệ thống",
        "table_cell_0_0_0": "Tên chức năng",
        "table_cell_0_1_0": "Xác thực người dùng",
        "docx_footer_0_0": "Trang 1 / 10"
    }

    DocxRenderer.render(
        working_path=docx_path,
        output_path=output_docx,
        segments_by_loc=segments_by_loc,
        tgt_lang="vi"
    )

    assert output_docx.exists()
    out_doc = docx.Document(str(output_docx))

    # Check header
    assert "MẬT - Tài liệu đặc tả dự án" in out_doc.sections[0].header.paragraphs[0].text

    # Check paragraph styling preserved
    out_p = out_doc.paragraphs[0]
    assert "Chương 1: Cấu trúc hệ thống" in out_p.text
    assert out_p.runs[0].bold is True
    assert out_p.runs[0].font.size == DocxPt(14)
    assert out_p.runs[0].font.color.rgb == DocxRGB(0x1F, 0x49, 0x7D)

    # Check table cell styling preserved
    out_table = out_doc.tables[0]
    out_hdr_cell = out_table.rows[0].cells[0]
    assert "Tên chức năng" in out_hdr_cell.text
    assert out_hdr_cell.paragraphs[0].runs[0].bold is True

    # Check footer
    assert "Trang 1 / 10" in out_doc.sections[0].footer.paragraphs[0].text


def test_docx_none_style_and_cjk_font_preservation(tmp_path):
    """Verifies that paragraphs with None style (e.g. corrupted/external styles) parse safely and render properly."""
    parser = DocxParser()

    # Test _get_paragraph_style_name with None style and XML fallback
    class MockPPr:
        class pStyle:
            @staticmethod
            def get(key):
                return "CustomStyleVal"

    class MockParagraph:
        style = None
        class _p:
            pPr = MockPPr()
        text = "Mock paragraph text"
        runs = []

    mock_p = MockParagraph()
    assert DocxParser._get_paragraph_style_name(mock_p) == "CustomStyleVal"

    # Test fallback when style and _p are None
    class MockParagraphNoPr:
        style = None
        _p = None
        text = "Mock paragraph no pr"
        runs = []
    assert DocxParser._get_paragraph_style_name(MockParagraphNoPr()) == "Normal"

    # If real world sample euc-production-data-integration-spec-ja.docx exists, verify full parsing
    euc_path = Path(r"E:\AutomationTranslate\data\documents\original\euc-production-data-integration-spec-ja.docx")
    if euc_path.exists():
        segments, meta = parser.parse(euc_path)
        assert len(segments) == 121
        assert meta["paragraph_count"] == 42
        assert any(s.formatting_meta.get("style_name") == "FirstParagraph" for s in segments)


@pytest.mark.asyncio
async def test_xlsx_column_autofit_and_wrap(tmp_path):
    xlsx_path = tmp_path / "source.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "MainData"

    # Set narrow column width
    ws.column_dimensions["A"].width = 8.0

    # Japanese cell
    cell = ws["A1"]
    cell.value = "概要"
    cell.font = XlsxFont(name="MS Gothic", size=11, bold=True)
    cell.fill = PatternFill(start_color="CCE5FF", end_color="CCE5FF", fill_type="solid")

    cell2 = ws["A2"]
    cell2.value = "短い注記"

    wb.save(str(xlsx_path))

    # Parse
    parser = XlsxParser()
    segments, meta = parser.parse(xlsx_path)
    assert len(segments) == 2

    # Render with expanded Vietnamese text
    output_xlsx = tmp_path / "translated.xlsx"
    segments_by_loc = {
        "excel_cell_MainData_1_1": "Bản tóm tắt chi tiết cấu trúc hệ thống và quy trình nghiệp vụ",
        "excel_cell_MainData_2_1": "Ghi chú ngắn"
    }

    await XlsxRenderer.render(
        working_path=xlsx_path,
        output_path=output_xlsx,
        segments_by_loc=segments_by_loc,
        options={"translate_sheet_names": False},
        tgt_lang="vi"
    )

    assert output_xlsx.exists()
    out_wb = openpyxl.load_workbook(str(output_xlsx))
    out_ws = out_wb["MainData"]

    out_cell = out_ws["A1"]
    assert "Bản tóm tắt chi tiết" in out_cell.value
    # Verify bold & fill preserved
    assert out_cell.font.bold is True
    assert out_cell.fill.start_color.rgb == "00CCE5FF" or "CCE5FF" in str(out_cell.fill.start_color.rgb)
    # Verify Japanese font replaced with Latin/Unicode Calibri
    assert out_cell.font.name.lower() == "calibri"
    # Verify wrap_text enabled
    assert out_cell.alignment.wrap_text is True

    # Verify column width auto-expanded beyond initial 8.0
    col_w = out_ws.column_dimensions["A"].width
    assert col_w > 15.0


@pytest.mark.asyncio
async def test_pptx_run_style_preservation_and_wrap(tmp_path):
    pptx_path = tmp_path / "source.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Add styled shape
    tx_box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    tf = tx_box.text_frame
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "重要マイルストーン"
    run.font.bold = True
    run.font.italic = True
    run.font.size = PptxPt(20)
    run.font.color.rgb = PptxRGB(220, 20, 60)  # Crimson red

    # Add table with styled cell
    shape = slide.shapes.add_table(rows=2, cols=1, left=Inches(1), top=Inches(3), width=Inches(4), height=Inches(1.5))
    table_cell = shape.table.rows[0].cells[0]
    tcp = table_cell.text_frame.paragraphs[0]
    tc_run = tcp.add_run()
    tc_run.text = "フェーズ進捗状況"
    tc_run.font.bold = True

    prs.save(str(pptx_path))

    # Parse
    parser = PptxParser()
    segments, meta = parser.parse(pptx_path)
    assert len(segments) >= 2

    # Render
    output_pptx = tmp_path / "translated.pptx"
    segments_by_loc = {
        "pptx_shape_text_0_0_0": "Các cột mốc quan trọng của dự án",
        "pptx_table_cell_0_1_0_0": "Tiến độ triển khai từng giai đoạn"
    }

    await PptxRenderer.render(
        working_path=pptx_path,
        output_path=output_pptx,
        segments_by_loc=segments_by_loc,
        options={"translate_images": False},
        tgt_lang="vi"
    )

    assert output_pptx.exists()
    out_prs = pptx.Presentation(str(output_pptx))
    out_slide = out_prs.slides[0]

    # Verify shape text frame word wrap & run style preservation
    out_shape = out_slide.shapes[0]
    assert out_shape.text_frame.word_wrap is True
    out_run = out_shape.text_frame.paragraphs[0].runs[0]
    assert "Các cột mốc quan trọng" in out_run.text
    assert out_run.font.bold is True
    assert out_run.font.italic is True
    assert out_run.font.color.rgb == PptxRGB(220, 20, 60)
    assert out_run.font.name == "Arial"

    # Verify table cell word wrap & run bold preservation
    out_tbl_shape = out_slide.shapes[1]
    out_cell = out_tbl_shape.table.rows[0].cells[0]
    assert out_cell.text_frame.word_wrap is True
    out_tc_run = out_cell.text_frame.paragraphs[0].runs[0]
    assert "Tiến độ triển khai" in out_tc_run.text
    assert out_tc_run.font.bold is True


def test_docx_drawing_textbox_preservation(tmp_path):
    docx_path = tmp_path / "textbox_source.docx"
    doc = docx.Document()
    doc.add_paragraph("Đoạn văn thông thường")

    # Construct a drawing textbox element in Word XML: w:r/w:drawing/.../w:txbxContent/w:p/w:r/w:t
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls
    p = doc.add_paragraph()
    r = p.add_run()
    # Add a txbxContent block
    txbx_xml = f"""
    <w:drawing {nsdecls('w')}>
      <w:txbxContent>
        <w:p>
          <w:r>
            <w:rPr><w:b/></w:rPr>
            <w:t>重要ノート：アーキテクチャ要件</w:t>
          </w:r>
        </w:p>
      </w:txbxContent>
    </w:drawing>
    """
    r._r.append(parse_xml(txbx_xml))
    doc.save(str(docx_path))

    # Parse
    parser = DocxParser()
    segments, meta = parser.parse(docx_path)
    tb_seg = next((s for s in segments if s.location.get("type") == "docx_textbox"), None)
    assert tb_seg is not None
    assert "重要ノート" in tb_seg.source_text

    # Render
    output_docx = tmp_path / "textbox_translated.docx"
    segments_by_loc = {
        "paragraph_0": "Đoạn văn thông thường đã dịch",
        "paragraph_1": "",
        "docx_textbox_0": "Ghi chú quan trọng: Yêu cầu kiến trúc"
    }

    DocxRenderer.render(
        working_path=docx_path,
        output_path=output_docx,
        segments_by_loc=segments_by_loc,
        tgt_lang="vi"
    )

    assert output_docx.exists()
    out_doc = docx.Document(str(output_docx))
    txbx_out = out_doc._body._element.xpath('.//w:txbxContent//w:p')
    assert len(txbx_out) >= 1
    p_wrap = docx.text.paragraph.Paragraph(txbx_out[0], out_doc)
    assert "Ghi chú quan trọng" in p_wrap.text
    # Run bold preserved
    assert p_wrap.runs[0].bold is True


@pytest.mark.asyncio
async def test_pptx_group_shapes_preservation(tmp_path):
    pptx_path = tmp_path / "grouped_source.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # Add two shapes then group them
    tb1 = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(1))
    tb1.text_frame.paragraphs[0].text = "フロントエンド (UI)"
    tb2 = slide.shapes.add_textbox(Inches(3.5), Inches(1), Inches(2), Inches(1))
    tb2.text_frame.paragraphs[0].text = "バックエンド (API)"

    # Group shapes
    grp = slide.shapes.add_group_shape([tb1, tb2])

    prs.save(str(pptx_path))

    # Parse
    parser = PptxParser()
    segments, meta = parser.parse(pptx_path)
    assert len(segments) >= 2
    assert any("フロントエンド" in s.source_text for s in segments)
    assert any("バックエンド" in s.source_text for s in segments)

    # Render
    output_pptx = tmp_path / "grouped_translated.pptx"
    segments_by_loc = {}
    for s in segments:
        loc = s.location
        if "フロントエンド" in s.source_text:
            segments_by_loc[f"pptx_shape_text_{loc['slide_index']}_{loc['shape_index']}_{loc['paragraph_index']}"] = "Giao diện người dùng (UI)"
        elif "バックエンド" in s.source_text:
            segments_by_loc[f"pptx_shape_text_{loc['slide_index']}_{loc['shape_index']}_{loc['paragraph_index']}"] = "Hệ thống phụ trợ (API)"

    await PptxRenderer.render(
        working_path=pptx_path,
        output_path=output_pptx,
        segments_by_loc=segments_by_loc,
        tgt_lang="vi"
    )

    assert output_pptx.exists()
    out_prs = pptx.Presentation(str(output_pptx))
    out_slide = out_prs.slides[0]

    # Verify group shape still exists and children are translated
    all_out_shapes = PptxRenderer._collect_all_shapes(out_slide.shapes)
    texts = [s.text_frame.text for _, s in all_out_shapes if s.has_text_frame]
    assert any("Giao diện người dùng" in t for t in texts)
    assert any("Hệ thống phụ trợ" in t for t in texts)


@pytest.mark.asyncio
async def test_xlsx_row_height_expansion(tmp_path):
    xlsx_path = tmp_path / "row_height_source.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    ws["A1"].value = "タイトル"
    # Row with multi-line translated text
    ws["A2"].value = "詳細説明"

    wb.save(str(xlsx_path))

    output_xlsx = tmp_path / "row_height_translated.xlsx"
    segments_by_loc = {
        "excel_cell_Sheet1_1_1": "Tiêu đề",
        "excel_cell_Sheet1_2_1": "Dòng 1: Mô tả tổng quan về dự án\nDòng 2: Chi tiết các yêu cầu kỹ thuật\nDòng 3: Thời gian bàn giao dự kiến\nDòng 4: Đánh giá bảo mật và chất lượng"
    }

    await XlsxRenderer.render(
        working_path=xlsx_path,
        output_path=output_xlsx,
        segments_by_loc=segments_by_loc,
        options={"translate_sheet_names": False},
        tgt_lang="vi"
    )

    assert output_xlsx.exists()
    out_wb = openpyxl.load_workbook(str(output_xlsx))
    out_ws = out_wb["Sheet1"]

    # Verify row height for row 2 expanded significantly to accommodate 4 lines
    r2_height = out_ws.row_dimensions[2].height
    assert r2_height is not None
    assert r2_height >= 50.0


def test_docx_inline_multi_run_preservation(tmp_path):
    docx_path = tmp_path / "inline_runs_source.docx"
    doc = docx.Document()

    # Create a paragraph with 3 runs with distinct styles: Run 0 normal, Run 1 bold & red, Run 2 italic
    p = doc.add_paragraph()
    r0 = p.add_run("Xin lưu ý: ")
    r1 = p.add_run("QUAN TRỌNG")
    r1.bold = True
    r1.font.color.rgb = DocxRGB(0xFF, 0x00, 0x00)
    r2 = p.add_run(" trước khi bàn giao.")
    r2.italic = True

    doc.save(str(docx_path))

    # Parse
    parser = DocxParser()
    segments, meta = parser.parse(docx_path)
    assert len(segments) == 1
    seg = segments[0]
    # Check that parser detected mixed styles and tagged runs
    assert "<r0>" in seg.source_text
    assert "<r1>" in seg.source_text
    assert "<r2>" in seg.source_text

    # Render with translated tagged text
    output_docx = tmp_path / "inline_runs_translated.docx"
    segments_by_loc = {
        "paragraph_0": "<r0>Vui lòng chú ý: </r0><r1>ĐẶC BIỆT QUAN TRỌNG</r1><r2> trước khi bàn giao dự án.</r2>"
    }

    DocxRenderer.render(
        working_path=docx_path,
        output_path=output_docx,
        segments_by_loc=segments_by_loc,
        tgt_lang="vi"
    )

    assert output_docx.exists()
    out_doc = docx.Document(str(output_docx))
    out_p = out_doc.paragraphs[0]
    assert len(out_p.runs) >= 3
    assert "Vui lòng chú ý" in out_p.runs[0].text
    # Run 1 retains bold and red color!
    assert "ĐẶC BIỆT QUAN TRỌNG" in out_p.runs[1].text
    assert out_p.runs[1].bold is True
    assert out_p.runs[1].font.color.rgb == DocxRGB(0xFF, 0x00, 0x00)
    # Run 2 retains italic!
    assert "trước khi bàn giao" in out_p.runs[2].text
    assert out_p.runs[2].italic is True


@pytest.mark.asyncio
async def test_pptx_inline_multi_run_preservation(tmp_path):
    pptx_path = tmp_path / "inline_pptx_source.pptx"
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    tx_box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    tf = tx_box.text_frame
    p = tf.paragraphs[0]
    r0 = p.add_run()
    r0.text = "ステータス: "
    r1 = p.add_run()
    r1.text = "承認済み"
    r1.font.bold = True
    r1.font.color.rgb = PptxRGB(0, 128, 0) # Green

    prs.save(str(pptx_path))

    # Parse
    parser = PptxParser()
    segments, meta = parser.parse(pptx_path)
    assert len(segments) == 1
    seg = segments[0]
    assert "<r0>" in seg.source_text and "<r1>" in seg.source_text

    # Render
    output_pptx = tmp_path / "inline_pptx_translated.pptx"
    segments_by_loc = {
        "pptx_shape_text_0_0_0": "<r0>Trạng thái: </r0><r1>ĐÃ PHÊ DUYỆT</r1>"
    }

    await PptxRenderer.render(
        working_path=pptx_path,
        output_path=output_pptx,
        segments_by_loc=segments_by_loc,
        tgt_lang="vi"
    )

    assert output_pptx.exists()
    out_prs = pptx.Presentation(str(output_pptx))
    out_p = out_prs.slides[0].shapes[0].text_frame.paragraphs[0]
    assert "Trạng thái:" in out_p.runs[0].text
    assert "ĐÃ PHÊ DUYỆT" in out_p.runs[1].text
    assert out_p.runs[1].font.bold is True
    assert out_p.runs[1].font.color.rgb == PptxRGB(0, 128, 0)


@pytest.mark.asyncio
async def test_pdf_toc_and_collision_clamping(tmp_path):
    pdf_path = tmp_path / "toc_source.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Set document TOC outline
    doc.set_toc([
        [1, "第1章 概要", 1],
        [2, "第1.1節 アーキテクチャ", 1]
    ])

    # Insert two adjacent blocks on page 1
    font_file = "C:/Windows/Fonts/msgothic.ttc"
    page.insert_textbox(
        fitz.Rect(50, 50, 400, 80),
        "第1章 概要",
        fontfile=font_file,
        fontname="msgothic",
        fontsize=14
    )
    page.insert_textbox(
        fitz.Rect(50, 85, 400, 120),
        "本システムの基本構成とサービス連携",
        fontfile=font_file,
        fontname="msgothic",
        fontsize=10
    )

    doc.save(str(pdf_path))
    doc.close()

    # Parse
    parser = PdfParser()
    segments, meta = parser.parse(pdf_path)
    toc_segs = [s for s in segments if s.location.get("type") == "pdf_toc"]
    assert len(toc_segs) == 2
    assert any("第1章" in s.source_text for s in toc_segs)

    # Render
    output_pdf = tmp_path / "toc_translated.pdf"
    text_segs = [s for s in segments if s.location.get("type") == "pdf_text_block"]
    segments_by_loc = {
        "pdf_toc_0": "Chương 1: Tổng quan",
        "pdf_toc_1": "Mục 1.1: Kiến trúc hệ thống",
        f"pdf_text_block_0_{text_segs[0].location['block_no']}": "Chương 1: Tổng quan dự án",
        f"pdf_text_block_0_{text_segs[1].location['block_no']}": "Cấu trúc cơ bản của hệ thống và liên kết dịch vụ microservices."
    }
    raw_segments = [
        {"location": text_segs[0].location, "text": segments_by_loc[f"pdf_text_block_0_{text_segs[0].location['block_no']}"]},
        {"location": text_segs[1].location, "text": segments_by_loc[f"pdf_text_block_0_{text_segs[1].location['block_no']}"]}
    ]

    await PdfRenderer.render(
        working_path=pdf_path,
        output_path=output_pdf,
        segments_by_loc=segments_by_loc,
        raw_segments=raw_segments,
        options={"translate_images": False},
        tgt_lang="vi"
    )

    assert output_pdf.exists()
    out_doc = fitz.open(str(output_pdf))
    new_toc = out_doc.get_toc()
    assert len(new_toc) == 2
    assert "Chương 1: Tổng quan" in new_toc[0][1]
    assert "Mục 1.1: Kiến trúc" in new_toc[1][1]
    out_doc.close()


@pytest.mark.asyncio
async def test_xlsx_merged_ranges_height_balancing(tmp_path):
    xlsx_path = tmp_path / "merged_source.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Summary"

    # Merge A2:C4 (3 rows merged)
    ws.merge_cells("A2:C4")
    ws["A2"].value = "複数行マージテキスト"

    wb.save(str(xlsx_path))

    output_xlsx = tmp_path / "merged_translated.xlsx"
    segments_by_loc = {
        "excel_cell_Summary_2_1": "Dòng 1: Báo cáo phân tích kiến trúc\nDòng 2: Danh sách các thành phần cần nâng cấp\nDòng 3: Đánh giá hiệu năng và bảo mật\nDòng 4: Kế hoạch triển khai giai đoạn tiếp theo\nDòng 5: Kết luận và kiến nghị"
    }

    await XlsxRenderer.render(
        working_path=xlsx_path,
        output_path=output_xlsx,
        segments_by_loc=segments_by_loc,
        options={"translate_sheet_names": False},
        tgt_lang="vi"
    )

    assert output_xlsx.exists()
    out_wb = openpyxl.load_workbook(str(output_xlsx))
    out_ws = out_wb["Summary"]

    # Verify rows 2, 3, 4 expanded total height to accommodate 5 lines
    total_merged_h = sum(out_ws.row_dimensions[r].height or 15.0 for r in range(2, 5))
    assert total_merged_h >= 60.0


