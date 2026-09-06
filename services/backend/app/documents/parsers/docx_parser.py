from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import docx
from app.documents.parsers.base import DocumentParser
from app.documents.segmenter import ParsedSegment, TokenProtector

class DocxParser(DocumentParser):
    """Parses Word (.docx) documents preserving paragraphs, headings, runs, and tables."""

    def parse(self, file_path: Path, options: Optional[Dict[str, Any]] = None) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        doc = docx.Document(str(file_path))
        segments: List[ParsedSegment] = []
        segment_index = 0
        current_heading = "General"

        # 1. Parse Paragraphs
        for p_idx, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text.strip()
            if not text:
                continue

            # Check if this paragraph is a heading to track hierarchical context
            if paragraph.style.name.startswith("Heading"):
                current_heading = text

            protected_text, token_map = TokenProtector.protect_tokens(text)
            
            # Formatting metadata
            has_bold = any(run.bold for run in paragraph.runs if run.bold)
            has_italic = any(run.italic for run in paragraph.runs if run.italic)

            segments.append(ParsedSegment(
                segment_index=segment_index,
                source_text=protected_text,
                location={"type": "paragraph", "p_index": p_idx},
                protected_tokens=token_map,
                context_hint=f"Section: {current_heading}",
                formatting_meta={
                    "style_name": paragraph.style.name,
                    "has_bold": has_bold,
                    "has_italic": has_italic
                }
            ))
            segment_index += 1

        # 2. Parse Tables
        for t_idx, table in enumerate(doc.tables):
            headers = []
            for r_idx, row in enumerate(table.rows):
                row_cells_text = [cell.text.strip() for cell in row.cells]
                if r_idx == 0:
                    headers = row_cells_text

                for c_idx, cell in enumerate(row.cells):
                    cell_text = cell.text.strip()
                    if not cell_text:
                        continue

                    header_hint = headers[c_idx] if c_idx < len(headers) and r_idx > 0 else "Header"
                    protected_text, token_map = TokenProtector.protect_tokens(cell_text)

                    segments.append(ParsedSegment(
                        segment_index=segment_index,
                        source_text=protected_text,
                        location={"type": "table_cell", "t_index": t_idx, "r_index": r_idx, "c_index": c_idx},
                        protected_tokens=token_map,
                        context_hint=f"Table {t_idx + 1} - Column: {header_hint}",
                        formatting_meta={"is_header_row": r_idx == 0}
                    ))
                    segment_index += 1

        metadata = {
            "unit_count": len(doc.paragraphs) + len(doc.tables),
            "unit_label": "elements",
            "paragraph_count": len(doc.paragraphs),
            "table_count": len(doc.tables),
            "total_segments": len(segments)
        }
        return segments, metadata
