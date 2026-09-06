from pathlib import Path
from typing import Dict, List, Any
import docx
from app.core.logging import logger

class DocxRenderer:
    """Renders translated text back into Word (.docx) document while preserving formatting."""

    @classmethod
    def render(cls, working_path: Path, output_path: Path, segments_by_loc: Dict[str, str]):
        doc = docx.Document(str(working_path))

        # 1. Update Paragraphs
        for p_idx, paragraph in enumerate(doc.paragraphs):
            loc_key = f"paragraph_{p_idx}"
            if loc_key in segments_by_loc:
                translated_text = segments_by_loc[loc_key]
                if paragraph.runs:
                    # Check if any runs contain inline images or shapes (<w:drawing>)
                    drawing_runs = [r for r in paragraph.runs if r._r.xpath(".//w:drawing")]
                    if not drawing_runs:
                        # Standard text-only paragraph: preserve first run formatting and replace text
                        paragraph.runs[0].text = translated_text
                        for r in paragraph.runs[1:]:
                            r.text = ""
                    else:
                        # Paragraph contains inline drawing: do NOT erase runs with drawings
                        text_placed = False
                        for r in paragraph.runs:
                            if not r._r.xpath(".//w:drawing"):
                                if not text_placed:
                                    r.text = translated_text
                                    text_placed = True
                                else:
                                    r.text = ""
                        if not text_placed:
                            paragraph.text = translated_text
                else:
                    paragraph.text = translated_text

        # 2. Update Tables
        for t_idx, table in enumerate(doc.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    loc_key = f"table_cell_{t_idx}_{r_idx}_{c_idx}"
                    if loc_key in segments_by_loc:
                        cell.text = segments_by_loc[loc_key]

        doc.save(str(output_path))
        logger.info(f"DOCX document successfully rendered to {output_path}")
