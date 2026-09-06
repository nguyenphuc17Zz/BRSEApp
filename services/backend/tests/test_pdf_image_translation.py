import pytest
import io
import pymupdf as fitz
from PIL import Image, ImageDraw
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.documents.parsers.pdf_parser import PdfParser
from app.documents.renderers.pdf_renderer import PdfRenderer


@pytest.fixture
def sample_pdf_with_image(tmp_path):
    """Creates a temporary PDF with Japanese text blocks and an embedded image."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842) # A4 size

    # 1. Insert text blocks with Japanese font
    font_file = "C:/Windows/Fonts/msgothic.ttc"
    page.insert_textbox(
        fitz.Rect(50, 50, 500, 80),
        "AWSクラウド基盤構成仕様書",
        fontfile=font_file,
        fontname="msgothic",
        fontsize=16
    )
    page.insert_textbox(
        fitz.Rect(50, 90, 500, 130),
        "本ドキュメントはマイクロサービス全体のインフラ構成を定義する。",
        fontfile=font_file,
        fontname="msgothic",
        fontsize=11
    )

    # 2. Insert synthetic architecture diagram image
    img = Image.new("RGB", (300, 150), color=(240, 248, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 120, 70], fill=(41, 128, 185))
    draw.text((30, 35), "API Gateway", fill=(255, 255, 255))
    draw.rectangle([160, 20, 280, 70], fill=(39, 174, 96))
    draw.text((180, 35), "ECS Fargate", fill=(255, 255, 255))

    img_stream = io.BytesIO()
    img.save(img_stream, format="PNG")
    img_bytes = img_stream.getvalue()

    # Insert into PDF page at Rect(50, 150, 450, 350)
    page.insert_image(fitz.Rect(50, 150, 450, 350), stream=img_bytes)

    pdf_path = tmp_path / "sample_arch.pdf"
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_pdf_parser_extracts_text_blocks(sample_pdf_with_image):
    parser = PdfParser()
    segments, metadata = parser.parse(sample_pdf_with_image)

    texts = [seg.source_text for seg in segments]
    assert any("AWSクラウド基盤構成仕様書" in t for t in texts)
    assert any("マイクロサービス" in t for t in texts)
    assert metadata["page_count"] == 1
    assert not metadata["is_scanned_pdf"]


@pytest.mark.asyncio
async def test_pdf_renderer_text_and_image_translation(sample_pdf_with_image, tmp_path):
    output_path = tmp_path / "translated_output.pdf"

    parser = PdfParser()
    segments, _ = parser.parse(sample_pdf_with_image)

    segments_by_loc = {}
    raw_segments = []
    for seg in segments:
        loc = seg.location
        key = f"pdf_text_block_{loc.get('page_index')}_{loc.get('block_no')}"
        if "AWSクラウド基盤構成仕様書" in seg.source_text:
            segments_by_loc[key] = "Tài liệu đặc tả kiến trúc đám mây AWS"
        else:
            segments_by_loc[key] = "Tài liệu này định nghĩa cấu trúc hạ tầng của toàn bộ microservices."
        raw_segments.append({"location": loc, "text": segments_by_loc[key]})

    # Create synthetic translated image (valid PNG)
    mod_img = Image.new("RGB", (300, 150), color=(250, 240, 230))
    buf = io.BytesIO()
    mod_img.save(buf, format="PNG")
    fake_new_image_bytes = buf.getvalue()

    with patch("app.documents.renderers.pdf_renderer.image_translator.process_image", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = fake_new_image_bytes

        await PdfRenderer.render(
            working_path=sample_pdf_with_image,
            output_path=output_path,
            segments_by_loc=segments_by_loc,
            raw_segments=raw_segments,
            options={"translate_images": True, "ocr_mode": "paddleocr"},
            src_lang="ja",
            tgt_lang="vi"
        )

        assert mock_process.await_count >= 1
        call_kwargs = mock_process.call_args.kwargs
        assert call_kwargs["src_lang"] == "ja"
        assert call_kwargs["tgt_lang"] == "vi"

    # Verify rendered PDF
    out_doc = fitz.open(str(output_path))
    assert len(out_doc) == 1
    page = out_doc[0]

    # Verify text blocks translated
    page_text = page.get_text().replace('\xa0', ' ')
    assert "Tài liệu đặc tả kiến trúc đám mây AWS" in page_text
    assert "toàn bộ microservices" in page_text

    # Verify image was replaced in-place
    images = page.get_images()
    assert len(images) >= 1
    # Check that the extracted image is valid and matches dimensions
    extracted = out_doc.extract_image(images[0][0])
    assert extracted["width"] == 300
    assert extracted["height"] == 150
    pil_img = Image.open(io.BytesIO(extracted["image"]))
    assert pil_img.size == (300, 150)
    out_doc.close()
