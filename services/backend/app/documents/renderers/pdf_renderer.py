import os
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import pymupdf as fitz  # PyMuPDF
from app.core.logging import logger
from app.documents.ocr.image_translator import image_translator

# Preferred Unicode fonts on Windows for Japanese and Latin/Vietnamese
# Preferred Unicode fonts on Windows for Japanese and Latin/Vietnamese
JAPANESE_FONTS = {
    "regular": [
        ("C:/Windows/Fonts/msgothic.ttc", "msgothic"),
        ("C:/Windows/Fonts/YuGothM.ttc", "yugothic"),
        ("C:/Windows/Fonts/YuGothR.ttc", "yugothic"),
        ("C:/Windows/Fonts/meiryo.ttc", "meiryo"),
    ],
    "bold": [
        ("C:/Windows/Fonts/YuGothB.ttc", "yugothic_bold"),
        ("C:/Windows/Fonts/meiryob.ttc", "meiryo_bold"),
        ("C:/Windows/Fonts/msgothic.ttc", "msgothic"),
    ]
}

VIETNAMESE_FONTS = {
    "regular": [
        ("C:/Windows/Fonts/arial.ttf", "arial_vn"),
        ("C:/Windows/Fonts/segoeui.ttf", "segoe_vn"),
        ("C:/Windows/Fonts/times.ttf", "times_vn"),
    ],
    "bold": [
        ("C:/Windows/Fonts/arialbd.ttf", "arial_bold_vn"),
        ("C:/Windows/Fonts/segoeuib.ttf", "segoe_bold_vn"),
        ("C:/Windows/Fonts/timesbd.ttf", "times_bold_vn"),
    ],
    "italic": [
        ("C:/Windows/Fonts/ariali.ttf", "arial_italic_vn"),
        ("C:/Windows/Fonts/segoeuii.ttf", "segoe_italic_vn"),
        ("C:/Windows/Fonts/timesi.ttf", "times_italic_vn"),
    ],
    "bold_italic": [
        ("C:/Windows/Fonts/arialbi.ttf", "arial_bi_vn"),
        ("C:/Windows/Fonts/segoeuiz.ttf", "segoe_bi_vn"),
        ("C:/Windows/Fonts/timesbi.ttf", "times_bi_vn"),
    ]
}


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
        """Replaces Japanese punctuation and full-width symbols with Latin/ASCII equivalents."""
        if not text:
            return ""
        s = text
        for ja_char, latin_char in cls._JA_SYMBOL_MAP:
            s = s.replace(ja_char, latin_char)
        return s

    @classmethod
    def _get_font_for_target(cls, tgt_lang: str, text: str = "", is_bold: bool = False, is_italic: bool = False) -> tuple:
        """Selects font file and fontname based on target language, glyph content, and bold/italic style."""
        has_cjk_after_sanitize = any(
            '\u3040' <= c <= '\u30ff' or  # Hiragana + Katakana
            '\u4e00' <= c <= '\u9fff' or  # CJK Unified Ideographs (Kanji/Hanzi)
            '\u3400' <= c <= '\u4dbf'     # CJK Extension A
            for c in (text or "")
        )
        has_vi = any(c in VI_DIACRITICS for c in (text or ""))
        is_tgt_vi = (tgt_lang or "").lower() in ("vi", "vietnamese", "viet")
        is_tgt_ja = (tgt_lang or "").lower() in ("ja", "japanese", "jp")

        style_key = "bold_italic" if (is_bold and is_italic) else ("bold" if is_bold else ("italic" if is_italic else "regular"))

        if has_cjk_after_sanitize:
            candidates = JAPANESE_FONTS.get("bold" if is_bold else "regular", JAPANESE_FONTS.get("regular", []))
            for fp, fname in candidates:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"
        elif is_tgt_vi or has_vi or is_tgt_ja is False:
            candidates = VIETNAMESE_FONTS.get(style_key) or VIETNAMESE_FONTS.get("regular", [])
            for fp, fname in candidates:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"
        elif is_tgt_ja:
            candidates = JAPANESE_FONTS.get("bold" if is_bold else "regular", JAPANESE_FONTS.get("regular", []))
            for fp, fname in candidates:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"
        else:
            candidates = VIETNAMESE_FONTS.get(style_key) or VIETNAMESE_FONTS.get("regular", [])
            for fp, fname in candidates:
                if os.path.exists(fp):
                    return fp, fname
            return None, "helv"

    @classmethod
    def _get_unicode_font(cls) -> Optional[str]:
        for fp, _ in VIETNAMESE_FONTS.get("regular", []):
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
        provider: Any = None,
        on_progress: Optional[Callable[[str], Any]] = None
    ):
        doc = fitz.open(str(working_path))
        opts = options or {}
        translate_images = opts.get("translate_images", True)
        ocr_mode = opts.get("ocr_mode", "auto")

        async def _notify(stage_desc: str):
            if on_progress:
                try:
                    if asyncio.iscoroutinefunction(on_progress):
                        await on_progress(stage_desc)
                    else:
                        on_progress(stage_desc)
                except Exception as p_err:
                    logger.debug(f"Progress notification notice: {p_err}")

        # 1. Update text blocks
        # 1. Two-pass text replacement:
        # Pass 1: Apply redactions with adaptive background color for all matched text blocks
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

                font_size = loc.get("font_size")
                font_color = loc.get("font_color") or [0.0, 0.0, 0.0]
                is_bold = bool(loc.get("is_bold", False))
                is_italic = bool(loc.get("is_italic", False))
                align = loc.get("align", 0)
                bg_color = loc.get("bg_color") or [1.0, 1.0, 1.0]

                # Redact with sampled background color to eliminate white rectangle patches
                fill_color = tuple(bg_color) if len(bg_color) == 3 else (1.0, 1.0, 1.0)
                page.add_redact_annot(rect, fill=fill_color)
                redacted_pages.add(page_idx)
                blocks_to_render.append((page_idx, rect, translated_text, font_size, font_color, is_bold, is_italic, align))

        # Apply all redactions per page once
        for p_idx in redacted_pages:
            doc[p_idx].apply_redactions()

        # Pass 2: Insert translated text preserving original font size, color, bold, alignment, and preventing collisions
        page_blocks: Dict[int, list] = {}
        for b in blocks_to_render:
            p_idx = b[0]
            if p_idx not in page_blocks:
                page_blocks[p_idx] = []
            page_blocks[p_idx].append(b)

        for p_idx, p_list in page_blocks.items():
            page = doc[p_idx]
            # Sort blocks by vertical position (y0)
            p_list.sort(key=lambda item: (item[1].y0, item[1].x0))

            for i, (page_idx, rect, text, font_size, font_color, is_bold, is_italic, align) in enumerate(p_list):
                try:
                    box_h = rect.height

                    # Determine starting font size from original typography
                    if font_size and font_size > 5.0:
                        init_fs = font_size
                    else:
                        init_fs = 14 if box_h >= 30 else (12 if box_h >= 15 else 9.5)

                    # Collision prevention: check distance to next block on same vertical column
                    max_allowed_y1 = max(rect.y1 + 4, rect.y0 + box_h * 1.15)
                    for j in range(i + 1, len(p_list)):
                        next_rect = p_list[j][1]
                        if next_rect.y0 > rect.y0 and max(rect.x0, next_rect.x0) < min(rect.x1, next_rect.x1):
                            dist = next_rect.y0 - rect.y1
                            if dist < 12:
                                max_allowed_y1 = min(max_allowed_y1, next_rect.y0 - 2)
                            break

                    target_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, max(rect.y0 + 6, max_allowed_y1))

                    # Sanitize CJK symbols for Latin/Vietnamese font compatibility
                    is_non_ja_target = (tgt_lang or "").lower() not in ("ja", "japanese", "jp")
                    if is_non_ja_target:
                        clean_text = cls.sanitize_for_latin_font(text or "")
                    else:
                        clean_text = (text or "").replace("　", " ")

                    # Select font file and font name respecting bold/italic
                    font_file, font_name = cls._get_font_for_target(
                        tgt_lang, clean_text, is_bold=is_bold, is_italic=is_italic
                    )

                    # Ensure original text color is preserved (not hardcoded to black)
                    text_color = tuple(font_color) if font_color and len(font_color) == 3 else (0.0, 0.0, 0.0)

                    # Auto-fit text: start from original size, gently reduce if Vietnamese text expands
                    min_fs = max(6.0, init_fs * 0.7)
                    for fs_int in range(int(init_fs * 2), int(min_fs * 2) - 1, -1):
                        fs = fs_int / 2.0
                        rc = page.insert_textbox(
                            target_rect,
                            clean_text,
                            fontfile=font_file,
                            fontname=font_name,
                            fontsize=fs,
                            color=text_color,
                            align=align
                        )
                        if rc >= 0:
                            break
                except Exception as e:
                    logger.warning(f"Error writing text to PDF page {page_idx + 1} rect {rect}: {e}")

        # 2. Process embedded images across all pages
        if translate_images:
            processed_xrefs = set()
            candidate_images = []
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
                            candidate_images.append((page_idx, xref, width, height, raw_bytes, page))
                    except Exception as ext_err:
                        logger.debug(f"Extract image xref={xref} notice: {ext_err}")

            total_imgs = len(candidate_images)
            for idx, (page_idx, xref, width, height, raw_bytes, page) in enumerate(candidate_images):
                await _notify(f"Đang dịch hình ảnh & sơ đồ ({idx + 1}/{total_imgs})...")
                logger.info(f"Processing PDF embedded image xref={xref} on page {page_idx + 1} ({width}x{height}, OCR: {ocr_mode}) [{idx + 1}/{total_imgs}]...")
                try:
                    new_bytes = await asyncio.wait_for(
                        image_translator.process_image(
                            image_bytes=raw_bytes,
                            src_lang=src_lang,
                            tgt_lang=tgt_lang,
                            ocr_engine=ocr_mode,
                            provider=provider
                        ),
                        timeout=25.0
                    )
                    if new_bytes and len(new_bytes) > 0 and new_bytes != raw_bytes:
                        page.replace_image(xref, stream=new_bytes)
                        logger.info(f"Successfully replaced image xref={xref} on PDF page {page_idx + 1} with translated version.")
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout (25s) translating image xref={xref} on PDF page {page_idx + 1}, keeping original.")
                except Exception as img_err:
                    logger.warning(f"Failed to translate embedded image xref={xref} on PDF page {page_idx + 1}: {img_err}")

        # 3. Reconstruct and apply translated Document Outline / Bookmarks (TOC)
        try:
            orig_toc = doc.get_toc()
            if orig_toc:
                new_toc = []
                for toc_idx, toc_item in enumerate(orig_toc):
                    loc_key = f"pdf_toc_{toc_idx}"
                    if loc_key in segments_by_loc:
                        new_toc.append([toc_item[0], segments_by_loc[loc_key], toc_item[2]])
                    else:
                        new_toc.append(toc_item)
                doc.set_toc(new_toc)
                logger.info(f"Updated {len(new_toc)} PDF bookmark titles in outline.")
        except Exception as toc_err:
            logger.debug(f"PDF TOC update notice: {toc_err}")

        await _notify("Đang lưu và đóng gói file PDF hoàn tất...")
        doc.save(str(output_path), deflate=True, garbage=3)
        logger.info(f"PDF document successfully rendered to {output_path}")
