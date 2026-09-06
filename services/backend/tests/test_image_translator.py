import pytest
import io
from PIL import Image, ImageDraw
from app.documents.ocr.image_translator import ImageTranslator

@pytest.mark.asyncio
async def test_image_translator_inpaint_and_overlay():
    translator = ImageTranslator()

    # 1. Create a synthetic test image with a white box and black text
    img = Image.new("RGB", (400, 200), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    # Draw a blue button box
    draw.rectangle([50, 50, 250, 110], fill=(41, 128, 185))
    # Draw sample text inside
    draw.text((70, 70), "ログイン", fill=(255, 255, 255))

    img_stream = io.BytesIO()
    img.save(img_stream, format="PNG")
    original_bytes = img_stream.getvalue()

    # 2. Mock detected labels
    labels = [
        {
            # Normalized box: ymin, xmin, ymax, xmax (scale 0-1000)
            # Box [50, 50, 250, 110]:
            # ymin = 50 / 200 * 1000 = 250
            # xmin = 50 / 400 * 1000 = 125
            # ymax = 110 / 200 * 1000 = 550
            # xmax = 250 / 400 * 1000 = 625
            "box_2d": [250, 125, 550, 625],
            "original_text": "ログイン",
            "translated_text": "Đăng nhập"
        }
    ]

    # 3. Test inpaint_and_overlay
    modified_bytes = translator.inpaint_and_overlay(original_bytes, labels, tgt_lang="vi")
    assert modified_bytes is not None
    assert len(modified_bytes) > 0

    # 4. Verify modified image can be opened and has same dimensions
    mod_img = Image.open(io.BytesIO(modified_bytes))
    assert mod_img.size == (400, 200)

@pytest.mark.asyncio
async def test_image_translator_empty_labels_returns_original():
    translator = ImageTranslator()
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    s = io.BytesIO()
    img.save(s, format="PNG")
    original_bytes = s.getvalue()

    res = translator.inpaint_and_overlay(original_bytes, [], tgt_lang="vi")
    assert res == original_bytes
