from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import docx
from app.documents.parsers.base import DocumentParser
from app.documents.segmenter import ParsedSegment, TokenProtector

class DocxParser(DocumentParser):
    """Parses Word (.docx) documents preserving paragraphs, headings, runs, and tables."""

    @classmethod
    def _format_paragraph_with_tags(cls, paragraph) -> Tuple[str, bool]:
        """If paragraph contains runs with mixed formatting (bold, italic, size, color),
        wraps each run in <r0>...</r0>, <r1>...</r1> tags to preserve inline styles."""
        if not hasattr(paragraph, "runs") or len(paragraph.runs) <= 1:
            return paragraph.text.strip(), False

        non_empty = [r for r in paragraph.runs if r.text and r.text.strip()]
        if len(non_empty) <= 1:
            return paragraph.text.strip(), False

        first = non_empty[0]
        has_mixed = False
        for r in non_empty[1:]:
            f1 = getattr(first, 'font', None)
            f2 = getattr(r, 'font', None)
            s_diff = getattr(f1, 'size', None) != getattr(f2, 'size', None)
            c1 = getattr(getattr(f1, 'color', None), 'rgb', None) if f1 else None
            c2 = getattr(getattr(f2, 'color', None), 'rgb', None) if f2 else None
            if r.bold != first.bold or r.italic != first.italic or s_diff or c1 != c2:
                has_mixed = True
                break

        if not has_mixed:
            return paragraph.text.strip(), False

        parts = []
        for idx, r in enumerate(paragraph.runs):
            if not r.text:
                continue
            parts.append(f"<r{idx}>{r.text}</r{idx}>")
        return "".join(parts).strip(), True

    @classmethod
    def _get_paragraph_style_name(cls, paragraph) -> str:
        """Safely retrieves style name from paragraph, falling back to raw XML pStyle or 'Normal'."""
        if getattr(paragraph, "style", None) is not None and getattr(paragraph.style, "name", None):
            return str(paragraph.style.name)
        try:
            pPr = getattr(getattr(paragraph, "_p", None), "pPr", None)
            pStyle = getattr(pPr, "pStyle", None)
            if pStyle is not None:
                val = pStyle.get(docx.oxml.ns.qn('w:val'))
                if val:
                    return str(val)
        except Exception:
            pass
        return "Normal"

    def parse(self, file_path: Path, options: Optional[Dict[str, Any]] = None) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        doc = docx.Document(str(file_path))
        segments: List[ParsedSegment] = []
        segment_index = 0
        current_heading = "General"

        # 1. Parse Paragraphs
        for p_idx, paragraph in enumerate(doc.paragraphs):
            formatted_text, has_mixed = self._format_paragraph_with_tags(paragraph)
            text = formatted_text if has_mixed else paragraph.text.strip()
            if not text:
                continue

            # Check if this paragraph is a heading to track hierarchical context
            style_name = self._get_paragraph_style_name(paragraph)
            if style_name.lower().startswith("heading") or "見出し" in style_name:
                current_heading = paragraph.text.strip()

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
                    "style_name": style_name,
                    "has_bold": has_bold,
                    "has_italic": has_italic,
                    "has_inline_tags": has_mixed
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
                    if cell.paragraphs:
                        f_text, c_mixed = self._format_paragraph_with_tags(cell.paragraphs[0])
                        cell_text = f_text if c_mixed else cell.text.strip()
                    else:
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

        # 3. Parse Headers and Footers from Sections
        for s_idx, section in enumerate(doc.sections):
            try:
                if section.header and not section.header.is_linked_to_previous:
                    for hp_idx, hp in enumerate(section.header.paragraphs):
                        htext = hp.text.strip()
                        if htext:
                            p_text, t_map = TokenProtector.protect_tokens(htext)
                            segments.append(ParsedSegment(
                                segment_index=segment_index,
                                source_text=p_text,
                                location={"type": "docx_header", "s_index": s_idx, "p_index": hp_idx},
                                protected_tokens=t_map,
                                context_hint=f"Section {s_idx + 1} Header",
                                formatting_meta={"is_header": True}
                            ))
                            segment_index += 1
            except Exception:
                pass

            try:
                if section.footer and not section.footer.is_linked_to_previous:
                    for fp_idx, fp in enumerate(section.footer.paragraphs):
                        ftext = fp.text.strip()
                        if ftext:
                            p_text, t_map = TokenProtector.protect_tokens(ftext)
                            segments.append(ParsedSegment(
                                segment_index=segment_index,
                                source_text=p_text,
                                location={"type": "docx_footer", "s_index": s_idx, "p_index": fp_idx},
                                protected_tokens=t_map,
                                context_hint=f"Section {s_idx + 1} Footer",
                                formatting_meta={"is_footer": True}
                            ))
                            segment_index += 1
            except Exception:
                pass

        # 4. Parse Drawing Text Boxes and Callouts (w:txbxContent)
        try:
            txbx_elements = doc._body._element.xpath('.//w:txbxContent//w:p')
            for tb_idx, p_elem in enumerate(txbx_elements):
                p_wrap = docx.text.paragraph.Paragraph(p_elem, doc)
                formatted_tb, tb_mixed = self._format_paragraph_with_tags(p_wrap)
                tb_text = formatted_tb if tb_mixed else p_wrap.text.strip()
                if not tb_text:
                    continue
                p_text, t_map = TokenProtector.protect_tokens(tb_text)
                segments.append(ParsedSegment(
                    segment_index=segment_index,
                    source_text=p_text,
                    location={"type": "docx_textbox", "tb_index": tb_idx},
                    protected_tokens=t_map,
                    context_hint=f"Text Box / Callout {tb_idx + 1}",
                    formatting_meta={"is_textbox": True, "has_inline_tags": tb_mixed}
                ))
                segment_index += 1
        except Exception:
            pass

        metadata = {
            "unit_count": len(doc.paragraphs) + len(doc.tables) + len(doc.sections),
            "unit_label": "elements",
            "paragraph_count": len(doc.paragraphs),
            "table_count": len(doc.tables),
            "section_count": len(doc.sections),
            "total_segments": len(segments)
        }
        return segments, metadata
