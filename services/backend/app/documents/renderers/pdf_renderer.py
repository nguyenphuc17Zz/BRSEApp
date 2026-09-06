import os
from pathlib import Path
from typing import Dict, Any, Optional
import pymupdf as fitz  # PyMuPDF
from app.core.logging import logger
from app.documents.ocr.image_translator import image_translator

# Preferred Unicode fonts on Windows for Japanese and Latin/Vietnamese
JAPANESE_FONTS = [
    ("C:/Windows/Fonts/msgothic.ttc", "msgothic"),
    ("C:/Windows/Fonts/YuGothM.ttc", "yugothic"),
    ("C:/Windows/Fonts/YuGothR.ttc", "yugothic"),
    ("C:/Windows/Fonts/meiryo.ttc", "meiryo"),
]

VIETNAMESE_FONTS = [
    ("C:/Windows/Fonts/arial.ttf", "arial_vn"),
    ("C:/Windows/Fonts/segoeui.ttf", "segoe_vn"),
    ("C:/Windows/Fonts/times.ttf", "times_vn"),
]


VI_DIACRITICS = set(
    "áàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵđ"
    "ÁÀẢÃẠẮẰẲẴẶẤẦẨẪẬÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴĐ"
)


class PdfRenderer:
    """Renders translated text into PDF using PyMuPDF bounding-box replacement and in-place image translation."""

    # Map of Japanese/CJK symbols -> Latin/ASCII safe equivalents for non-Japanese target output
    _JA_SYMBOL_MAP = [
        ("円", " yên"),
        ("¥", " yên"),
        ("・", "• "),
        ("※", "* "),
        ("【", "["),
        ("】", "]"),
        ("「", '"'),
        ("」", '"'),
        ("『", '"'),
        ("』", '"'),
        ("〜", "~"),
        ("〇", "O"),
        ("→", "->"),
        ("←", "<-"),
        ("↑", "^"),
        ("↓", "v"),
        ("×", "x"),
        ("△", "^"),
        ("▲", "^"),
        ("▼", "v"),
        ("◎", "@"),
        ("●", "•"),
        ("○", "o"),
        ("■", "■"),   # keep safe box
        ("□", "[ ]"),
        ("　", " "),  # full-width space
    ]

    @classmethod
    def sanitize_for_latin_font(cls, text: str) -> str:
        """Replaces Japanese/CJK symbols with Latin-safe equivalents to prevent missing glyph (☐) rendering."""
        for src, dst in cls._JA_SYMBOL_MAP:
            text = text.replace(src, dst)
        return text

    @classmethod
    def _get_font_for_target(cls, tgt_lang: str, text: str = "") -> tuple:
        """Selects font file and fontname based on target language and actual text glyph content.
        
        Key insight: Called AFTER sanitize_for_latin_font() has already replaced CJK symbols
        (円, ※, 〜, etc.) with Latin equivalents. So `text` here reflects the ACTUAL characters
        that will be rendered.
        
        Decision tree:
        1. If text STILL has CJK chars (real Kanji/Kana/Hanzi after sanitize) -> MUST use Japanese font.
           This handles untranslated segments or mixed content to avoid square boxes.
        2. Else if tgt_lang is Vietnamese OR text has Vietnamese diacritics -> use Vietnamese/Latin font.
        3. Else if tgt_lang is Japanese -> use Japanese font.
        4. Fallback: Latin/Vietnamese font.
        """
        # Check for remaining CJK after sanitization (real Kanji U+4E00-9FFF, Hiragana, Katakana)
        has_cjk_after_sanitize = any(
            '\u3040' <= c <= '\u30ff' or  # Hiragana + Katakana
            '\u4e00' <= c <= '\u9fff' or  # CJK Unified Ideographs (Kanji/Hanzi)
            '\u3400' <= c <= '\u4dbf'     # CJK Extension A
            for c in (text or "")
        )
        has_vi = any(c in VI_DIACRITICS for c in (text or ""))
        is_tgt_vi = (tgt_lang or "").lower() in ("vi", "vietnamese", "viet")
        is_tgt_ja = (tgt_lang or "").lower() in ("ja", "japanese", "jp")

        if has_cjk_after_sanitize:
            # Text still contains real CJK characters (Kanji, Kana) - must use Japanese font
            # to avoid rendering them as square boxes, regardless of target language.
            for fp, fname in JAPANESE_FONTS:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"
        elif is_tgt_vi or has_vi:
            # Pure Vietnamese/Latin text: use Arial or Segoe UI (supports all diacritics)
            for fp, fname in VIETNAMESE_FONTS:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"
        elif is_tgt_ja:
            for fp, fname in JAPANESE_FONTS:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"
        else:
            # Generic Latin content
            for fp, fname in VIETNAMESE_FONTS:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"

    @classmethod
    def _get_unicode_font(cls) -> Optional[str]:
        for fp, _ in VIETNAMESE_FONTS:
            if os.path.exists(fp):
                return fp
        return None

    @classmethod
    async def render(
        cls,
        working_path: Path,
        output_path: Path,
        segments_by_loc: Dict[str, str],
        raw_segments: list,
        options: Optional[Dict[str, Any]] = None,
        src_lang: str = "ja",
        tgt_lang: str = "vi",
        provider: Any = None
    ):
        doc = fitz.open(str(working_path))
        opts = options or {}
        translate_images = opts.get("translate_images", True)
        ocr_mode = opts.get("ocr_mode", "auto")

        # 1. Update text blocks
        # 1. Two-pass text replacement:
        # Pass 1: Apply redactions for all matched text blocks across pages
        blocks_to_render = []
        redacted_pages = set()

        for seg in raw_segments:
            loc = seg.get("location", {})
            if loc.get("type") != "pdf_text_block":
                continue

            page_idx = loc.get("page_index", 0)
            block_no = loc.get("block_no", 0)
            bbox = loc.get("bbox", [])
            loc_key = f"pdf_text_block_{page_idx}_{block_no}"

            if loc_key in segments_by_loc and page_idx < len(doc) and len(bbox) == 4:
                translated_text = segments_by_loc[loc_key]
                rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
                page = doc[page_idx]
                page.add_redact_annot(rect, fill=(1, 1, 1))
                redacted_pages.add(page_idx)
                blocks_to_render.append((page_idx, rect, translated_text))

        # Apply all redactions per page once
        for p_idx in redacted_pages:
            doc[p_idx].apply_redactions()

        # Pass 2: Insert translated text with auto-fitting font size
        for page_idx, rect, text in blocks_to_render:
            try:
                page = doc[page_idx]
                box_h = rect.height
                init_fs = 14 if box_h >= 30 else (12 if box_h >= 15 else 9.5)
                # Modest breathing room for multi-line flow without overlapping subsequent sections
                target_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, max(rect.y1 + 4, rect.y0 + box_h * 1.12))

                # Sanitize CJK symbols for Latin/Vietnamese font compatibility
                # For non-Japanese targets, replace all Japanese symbols with ASCII/Latin equivalents
                # to prevent missing glyph (☐) rendering bugs.
                is_non_ja_target = (tgt_lang or "").lower() not in ("ja", "japanese", "jp")
                if is_non_ja_target:
                    clean_text = cls.sanitize_for_latin_font(text or "")
                else:
                    clean_text = (text or "").replace("　", " ")

                # Select font file and font name based on target language & actual text glyphs
                font_file, font_name = cls._get_font_for_target(tgt_lang, clean_text)

                # Auto-fit text: reduce font size until it fits into target_rect (rc >= 0)
                for fs_int in range(int(init_fs * 2), 11, -1):
                    fs = fs_int / 2.0
                    rc = page.insert_textbox(
                        target_rect,
                        clean_text,
                        fontfile=font_file,
                        fontname=font_name,
                        fontsize=fs,
                        color=(0, 0, 0)
                    )
                    if rc >= 0:
                        break
            except Exception as e:
                logger.warning(f"Error writing text to PDF page {page_idx + 1} rect {rect}: {e}")

        # 2. Process embedded images across all pages
        if translate_images:
            processed_xrefs = set()
            for page_idx, page in enumerate(doc):
                image_list = page.get_images()
                for img_info in image_list:
                    xref = img_info[0]
                    if xref in processed_xrefs:
                        continue
                    processed_xrefs.add(xref)

                    try:
                        base_image = doc.extract_image(xref)
                        if not base_image:
                            continue

                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        # Skip small icons/decorations
                        if width < 60 or height < 60:
                            continue

                        raw_bytes = base_image.get("image")
                        if raw_bytes:
                            logger.info(f"Processing PDF embedded image xref={xref} on page {page_idx + 1} ({width}x{height}, OCR: {ocr_mode})...")
                            new_bytes = await image_translator.process_image(
                                image_bytes=raw_bytes,
                                src_lang=src_lang,
                                tgt_lang=tgt_lang,
                                ocr_engine=ocr_mode,
                                provider=provider
                            )
                            if new_bytes and len(new_bytes) > 0 and new_bytes != raw_bytes:
                                page.replace_image(xref, stream=new_bytes)
                                logger.info(f"Successfully replaced image xref={xref} on PDF page {page_idx + 1} with translated version.")
                    except Exception as img_err:
                        logger.warning(f"Failed to translate embedded image xref={xref} on PDF page {page_idx + 1}: {img_err}")

        doc.save(str(output_path), deflate=True, garbage=3)
        logger.info(f"PDF document successfully rendered to {output_path}")
