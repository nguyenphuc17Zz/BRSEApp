import io
import os
import re
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import pptx
from pptx.util import Pt
from pptx.oxml.ns import qn
from PIL import Image

from app.core.logging import logger
from app.documents.ocr.image_translator import image_translator


class PptxRenderer:
    """Renders translated text into PowerPoint (.pptx) presentations with overflow handling and in-place image translation."""

    @classmethod
    def _replace_pptx_paragraph_runs(cls, paragraph: Any, new_text: str, is_vi: bool = True, font_name: str = "Arial"):
        """Preserves bold, italic, font color, size, and layout while replacing run text."""
        if not paragraph.runs:
            paragraph.text = re.sub(r"</?r\d+>", "", new_text)
            for r in paragraph.runs:
                r.font.name = font_name
            return

        # 1. Inline multi-run tags: <r0>...</r0><r1>...</r1>
        tag_pattern = re.compile(r"<r(\d+)>(.*?)</r\1>", re.DOTALL)
        tag_matches = list(tag_pattern.finditer(new_text))
        if tag_matches:
            tag_map = {int(m.group(1)): m.group(2) for m in tag_matches}
            for idx, r in enumerate(paragraph.runs):
                if idx in tag_map:
                    r.text = tag_map[idx]
                    r.font.name = font_name
                else:
                    r.text = ""
            return

        # 2. Fallback: clean any dropped tags and apply single-run preservation
        clean_text = re.sub(r"</?r\d+>", "", new_text)
        old_len = len(paragraph.text)
        first_run = paragraph.runs[0]

        # Preserve typography attributes from original run
        orig_bold = first_run.font.bold
        orig_italic = first_run.font.italic
        orig_size = first_run.font.size
        orig_rgb = None
        orig_theme_color = None
        try:
            if first_run.font.color and first_run.font.color.type is not None:
                orig_rgb = first_run.font.color.rgb
            elif first_run.font.color:
                orig_theme_color = first_run.font.color.theme_color
        except Exception:
            pass

        first_run.text = clean_text
        first_run.font.name = font_name
        if orig_bold is not None:
            first_run.font.bold = orig_bold
        if orig_italic is not None:
            first_run.font.italic = orig_italic

        # Proportional font scaling if Vietnamese expansion might exceed shape boundaries
        if orig_size:
            if len(new_text) > max(1, old_len) * 1.35:
                first_run.font.size = Pt(max(8.0, orig_size.pt * 0.9))
            else:
                first_run.font.size = orig_size

        if orig_rgb is not None:
            try:
                first_run.font.color.rgb = orig_rgb
            except Exception:
                pass
        elif orig_theme_color is not None:
            try:
                first_run.font.color.theme_color = orig_theme_color
            except Exception:
                pass

        # Clear subsequent runs to eliminate mixed or broken Japanese run fragments
        for r in paragraph.runs[1:]:
            r.text = ""

    @classmethod
    def _collect_all_shapes(cls, shapes_collection):
        """Recursively flattens slide shapes and nested GroupShapes into a list of (shape_key, shape)."""
        collected = []

        def _traverse(container, prefix):
            for idx, shp in enumerate(container):
                curr_key = f"{prefix}_{idx}" if prefix else str(idx)
                is_group = False
                try:
                    from pptx.enum.shapes import MSO_SHAPE_TYPE
                    is_group = (shp.shape_type == MSO_SHAPE_TYPE.GROUP)
                except Exception:
                    pass
                if is_group and hasattr(shp, "shapes"):
                    _traverse(shp.shapes, curr_key)
                else:
                    collected.append((curr_key, shp))

        _traverse(shapes_collection, "")
        return collected

    @classmethod
    async def render(
        cls,
        working_path: Path,
        output_path: Path,
        segments_by_loc: Dict[str, str],
        options: Optional[Dict[str, Any]] = None,
        src_lang: str = "ja",
        tgt_lang: str = "vi",
        provider: Any = None,
        on_progress: Optional[Callable[[str], Any]] = None
    ):
        prs = pptx.Presentation(str(working_path))
        opts = options or {}
        translate_images = opts.get("translate_images", True)
        ocr_mode = opts.get("ocr_mode", "auto")
        is_vi = (tgt_lang or "").lower() in ("vi", "vietnamese")
        font_name = "Arial" if is_vi else "MS Gothic"

        for slide_idx, slide in enumerate(prs.slides):
            # 1. Shapes & Text frames (recursively traversing GroupShapes)
            flat_shapes = cls._collect_all_shapes(slide.shapes)
            for shape_key, shape in flat_shapes:
                if shape.has_text_frame:
                    try:
                        shape.text_frame.word_wrap = True
                    except Exception:
                        pass
                    for p_idx, paragraph in enumerate(shape.text_frame.paragraphs):
                        loc_key = f"pptx_shape_text_{slide_idx}_{shape_key}_{p_idx}"
                        if loc_key in segments_by_loc:
                            new_text = segments_by_loc[loc_key]
                            if is_vi:
                                new_text = new_text.replace("・", "• ")
                            cls._replace_pptx_paragraph_runs(paragraph, new_text, is_vi=is_vi, font_name=font_name)

                # Tables in slide or within group shapes
                elif shape.has_table:
                    for r_idx, row in enumerate(shape.table.rows):
                        for c_idx, cell in enumerate(row.cells):
                            loc_key = f"pptx_table_cell_{slide_idx}_{shape_key}_{r_idx}_{c_idx}"
                            if loc_key in segments_by_loc:
                                new_text = segments_by_loc[loc_key]
                                if is_vi:
                                    new_text = new_text.replace("・", "• ")
                                try:
                                    cell.text_frame.word_wrap = True
                                except Exception:
                                    pass
                                if cell.text_frame.paragraphs:
                                    cls._replace_pptx_paragraph_runs(
                                        cell.text_frame.paragraphs[0],
                                        new_text,
                                        is_vi=is_vi,
                                        font_name=font_name
                                    )
                                    for extra_p in cell.text_frame.paragraphs[1:]:
                                        extra_p.text = ""
                                else:
                                    cell.text = new_text

            # 2. Speaker Notes
            if slide.has_notes_slide:
                notes_tf = slide.notes_slide.notes_text_frame
                if notes_tf:
                    for p_idx, paragraph in enumerate(notes_tf.paragraphs):
                        loc_key = f"pptx_speaker_notes_{slide_idx}_{p_idx}"
                        if loc_key in segments_by_loc:
                            new_text = segments_by_loc[loc_key]
                            if is_vi:
                                new_text = new_text.replace("・", "• ")
                            cls._replace_pptx_paragraph_runs(paragraph, new_text, is_vi=is_vi, font_name=font_name)

        # 3. In-place Image Translation across slides
        if translate_images:
            processed_rIds = set()
            images_to_process = []
            for slide_idx, slide in enumerate(prs.slides):
                for shape in slide.shapes:
                    blips = []
                    try:
                        blips = shape._element.xpath('.//a:blip')
                    except Exception:
                        pass

                    for blip in blips:
                        rId = getattr(blip, "rEmbed", None) or blip.get(qn('r:embed'))
                        if not rId or rId in processed_rIds:
                            continue
                        processed_rIds.add(rId)
                        images_to_process.append((slide_idx, slide, rId))

            total_imgs = len(images_to_process)
            for idx, (slide_idx, slide, rId) in enumerate(images_to_process):
                if on_progress:
                    try:
                        if asyncio.iscoroutinefunction(on_progress):
                            await on_progress(f"Đang dịch hình ảnh trình chiếu ({idx + 1}/{total_imgs})...")
                        else:
                            res = on_progress(f"Đang dịch hình ảnh trình chiếu ({idx + 1}/{total_imgs})...")
                            if asyncio.iscoroutine(res):
                                await res
                    except Exception:
                        pass

                try:
                    img_part = slide.part.related_part(rId)
                    if not img_part or not hasattr(img_part, "blob"):
                        continue

                    raw_bytes = img_part.blob
                    pil_temp = Image.open(io.BytesIO(raw_bytes))
                    if pil_temp.width < 60 or pil_temp.height < 60:
                        continue

                    logger.info(
                        f"Processing PPTX embedded image on slide {slide_idx + 1} "
                        f"({pil_temp.width}x{pil_temp.height}, OCR: {ocr_mode})..."
                    )
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
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout (25s) translating PPTX image {rId} on slide {slide_idx + 1}, skipping.")
                        continue

                    if new_bytes and len(new_bytes) > 0 and new_bytes != raw_bytes:
                        img_part._blob = new_bytes
                        logger.info(
                            f"Successfully replaced image {rId} on slide {slide_idx + 1} "
                            f"with translated version."
                        )
                except Exception as img_err:
                    logger.warning(
                        f"Failed to translate embedded image {rId} on slide {slide_idx + 1}: {img_err}"
                    )

        prs.save(str(output_path))
        logger.info(f"PPTX presentation successfully rendered to {output_path}")
