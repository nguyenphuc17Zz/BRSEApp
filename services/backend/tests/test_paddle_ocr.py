import pytest
import io
import numpy as np
from PIL import Image, ImageDraw
from app.documents.ocr.paddle_ocr_engine import paddle_ocr_engine

def test_paddle_ocr_engine_detection():
    # 1. Create a synthetic test image with clear text
    img = Image.new("RGB", (600, 250), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw Japanese and English labels
    draw.rectangle([50, 40, 260, 90], outline=(0, 0, 0), width=2)
    draw.text((70, 55), "API Gateway", fill=(0, 0, 0))

    draw.rectangle([50, 120, 260, 170], outline=(0, 0, 0), width=2)
    draw.text((70, 135), "データベース (DB)", fill=(0, 0, 0))

    s = io.BytesIO()
    img.save(s, format="PNG")
    img_bytes = s.getvalue()

    # 2. Run detection with PaddleOCREngine
    results = paddle_ocr_engine.detect_and_recognize(img_bytes)

    assert isinstance(results, list)
    assert len(results) >= 1
    # Check bounding box normalization to 0-1000
    for r in results:
        assert "box_2d" in r
        assert len(r["box_2d"]) == 4
        ymin, xmin, ymax, xmax = r["box_2d"]
        assert 0 <= ymin <= 1000
        assert 0 <= xmin <= 1000
        assert 0 <= ymax <= 1000
        assert 0 <= xmax <= 1000
        assert "original_text" in r
        assert "confidence" in r

def test_paddle_ocr_empty_image():
    blank = Image.new("RGB", (100, 100), color=(255, 255, 255))
    s = io.BytesIO()
    blank.save(s, format="PNG")
    res = paddle_ocr_engine.detect_and_recognize(s.getvalue())
    assert res == []
