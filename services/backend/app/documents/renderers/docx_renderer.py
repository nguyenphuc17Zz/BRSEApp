import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import docx
from app.core.logging import logger

class DocxRenderer:
    """Renders translated text back into Word (.docx) document while preserving formatting, table cell typography, and headers/footers."""

    @classmethod
    def _replace_paragraph_runs(cls, paragraph: Any, translated_text: str, tgt_lang: str = "vi"):
        """Replaces text in a paragraph while preserving font size, bold, italic, color, and drawing elements."""
        if not paragraph.runs:
            paragraph.text = re.sub(r"</?r\d+>", "", translated_text)
            return

        is_vi = (tgt_lang or "").lower() in ("vi", "vietnamese", "viet")
        cjk_font_indicators = ("gothic", "mincho", "meiryo", "yu gothic", "simsun", "ms ", "songti", "heiti")

        def _ensure_vi_font(run_obj):
            if not is_vi:
                return
            f = getattr(run_obj, "font", None)
            if f and getattr(f, "name", None) and any(ind in f.name.lower() for ind in cjk_font_indicators):
                f.name = "Arial"

        # 1. Check for inline multi-run tags: <r0>...</r0><r1>...</r1>
        tag_pattern = re.compile(r"<r(\d+)>(.*?)</r\1>", re.DOTALL)
        tag_matches = list(tag_pattern.finditer(translated_text))

        if tag_matches:
            tag_map = {int(m.group(1)): m.group(2) for m in tag_matches}
            for idx, r in enumerate(paragraph.runs):
                if idx in tag_map:
                    val = tag_map[idx]
                    _ensure_vi_font(r)
                    r.text = val
                else:
                    if not r._r.xpath(".//w:drawing"):
                        r.text = ""
            return

        # 2. Fallback: clean any dropped tags and preserve first run formatting
        clean_text = re.sub(r"</?r\d+>", "", translated_text)
        drawing_runs = [r for r in paragraph.runs if r._r.xpath(".//w:drawing")]
        if not drawing_runs:
            first_run = paragraph.runs[0]
            _ensure_vi_font(first_run)
            first_run.text = clean_text
            for r in paragraph.runs[1:]:
                r.text = ""
        else:
            text_placed = False
            for r in paragraph.runs:
                if not r._r.xpath(".//w:drawing"):
                    if not text_placed:
                        _ensure_vi_font(r)
                        r.text = clean_text
                        text_placed = True
                    else:
                        r.text = ""
            if not text_placed and clean_text:
                new_r = paragraph.add_run(clean_text)
                _ensure_vi_font(new_r)

    @classmethod
    def render(
        cls,
        working_path: Path,
        output_path: Path,
        segments_by_loc: Dict[str, str],
        tgt_lang: str = "vi"
    ):
        doc = docx.Document(str(working_path))

        # 1. Update Paragraphs
        for p_idx, paragraph in enumerate(doc.paragraphs):
            loc_key = f"paragraph_{p_idx}"
            if loc_key in segments_by_loc:
                cls._replace_paragraph_runs(paragraph, segments_by_loc[loc_key], tgt_lang=tgt_lang)

        # 2. Update Tables (preserving cell styling, font sizes, colors, and borders)
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    loc_key = f"table_cell_{t_idx}_{r_idx}_{c_idx}"
                    if loc_key in segments_by_loc:
                        translated_text = segments_by_loc[loc_key]
                        if cell.paragraphs:
                            cls._replace_paragraph_runs(cell.paragraphs[0], translated_text, tgt_lang=tgt_lang)
                            for extra_p in cell.paragraphs[1:]:
                                extra_p.text = ""
                        else:
                            cell.text = translated_text

        # 3. Update Headers & Footers
        for s_idx, section in enumerate(doc.sections):
            try:
                if section.header:
                    for hp_idx, hp in enumerate(section.header.paragraphs):
                        loc_key = f"docx_header_{s_idx}_{hp_idx}"
                        if loc_key in segments_by_loc:
                            cls._replace_paragraph_runs(hp, segments_by_loc[loc_key], tgt_lang=tgt_lang)
            except Exception as h_err:
                logger.debug(f"Header render notice section {s_idx}: {h_err}")

            try:
                if section.footer:
                    for fp_idx, fp in enumerate(section.footer.paragraphs):
                        loc_key = f"docx_footer_{s_idx}_{fp_idx}"
                        if loc_key in segments_by_loc:
                            cls._replace_paragraph_runs(fp, segments_by_loc[loc_key], tgt_lang=tgt_lang)
            except Exception as f_err:
                logger.debug(f"Footer render notice section {s_idx}: {f_err}")

        # 4. Update Drawing Text Boxes & Callouts (w:txbxContent)
        try:
            txbx_elements = doc._body._element.xpath('.//w:txbxContent//w:p')
            for tb_idx, p_elem in enumerate(txbx_elements):
                loc_key = f"docx_textbox_{tb_idx}"
                if loc_key in segments_by_loc:
                    p_wrap = docx.text.paragraph.Paragraph(p_elem, doc)
                    cls._replace_paragraph_runs(p_wrap, segments_by_loc[loc_key], tgt_lang=tgt_lang)
        except Exception as tb_err:
            logger.debug(f"Textbox render notice: {tb_err}")

        doc.save(str(output_path))
        logger.info(f"DOCX document successfully rendered to {output_path}")
