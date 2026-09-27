from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import pptx
from app.documents.parsers.base import DocumentParser
from app.documents.segmenter import ParsedSegment, TokenProtector

class PptxParser(DocumentParser):
    """Parses PowerPoint (.pptx) presentations preserving slide structure, shapes, tables, and notes."""

    @classmethod
    def _collect_all_shapes(cls, shapes_collection) -> List[Tuple[str, Any]]:
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
            b1 = getattr(f1, 'bold', None) if f1 else None
            b2 = getattr(f2, 'bold', None) if f2 else None
            i1 = getattr(f1, 'italic', None) if f1 else None
            i2 = getattr(f2, 'italic', None) if f2 else None
            if b1 != b2 or i1 != i2 or s_diff:
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

    def parse(self, file_path: Path, options: Optional[Dict[str, Any]] = None) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        prs = pptx.Presentation(str(file_path))
        opts = options or {}
        translate_notes = opts.get("translate_notes", True)

        segments: List[ParsedSegment] = []
        segment_index = 0

        for slide_idx, slide in enumerate(prs.slides):
            # Extract slide title if present to provide structured context
            slide_title = f"Slide {slide_idx + 1}"
            if slide.shapes.title and slide.shapes.title.text.strip():
                slide_title = slide.shapes.title.text.strip()

            # 1. Parse Shapes & Text Frames (recursively including GroupShapes)
            flat_shapes = self._collect_all_shapes(slide.shapes)
            for shape_key, shape in flat_shapes:
                if shape.has_text_frame:
                    for p_idx, paragraph in enumerate(shape.text_frame.paragraphs):
                        f_text, has_mixed = self._format_paragraph_with_tags(paragraph)
                        text = f_text if has_mixed else paragraph.text.strip()
                        if not text:
                            continue

                        protected_text, token_map = TokenProtector.protect_tokens(text)
                        segments.append(ParsedSegment(
                            segment_index=segment_index,
                            source_text=protected_text,
                            location={
                                "type": "pptx_shape_text",
                                "slide_index": slide_idx,
                                "shape_index": shape_key,
                                "paragraph_index": p_idx
                            },
                            protected_tokens=token_map,
                            context_hint=f"Slide {slide_idx + 1}: {slide_title}",
                            formatting_meta={
                                "is_title": shape == slide.shapes.title,
                                "font_size": paragraph.font.size.pt if paragraph.font and paragraph.font.size else None,
                                "has_inline_tags": has_mixed
                            }
                        ))
                        segment_index += 1

                # Tables inside slides or group shapes
                elif shape.has_table:
                    for r_idx, row in enumerate(shape.table.rows):
                        for c_idx, cell in enumerate(row.cells):
                            text = cell.text.strip()
                            if not text:
                                continue

                            protected_text, token_map = TokenProtector.protect_tokens(text)
                            segments.append(ParsedSegment(
                                segment_index=segment_index,
                                source_text=protected_text,
                                location={
                                    "type": "pptx_table_cell",
                                    "slide_index": slide_idx,
                                    "shape_index": shape_key,
                                    "row_index": r_idx,
                                    "col_index": c_idx
                                },
                                protected_tokens=token_map,
                                context_hint=f"Slide {slide_idx + 1} Table - Row {r_idx + 1}, Col {c_idx + 1}",
                                formatting_meta={"is_table": True}
                            ))
                            segment_index += 1

            # 2. Speaker Notes
            if translate_notes and slide.has_notes_slide:
                notes_text_frame = slide.notes_slide.notes_text_frame
                if notes_text_frame and notes_text_frame.text.strip():
                    for p_idx, paragraph in enumerate(notes_text_frame.paragraphs):
                        text = paragraph.text.strip()
                        if not text:
                            continue

                        protected_text, token_map = TokenProtector.protect_tokens(text)
                        segments.append(ParsedSegment(
                            segment_index=segment_index,
                            source_text=protected_text,
                            location={
                                "type": "pptx_speaker_notes",
                                "slide_index": slide_idx,
                                "paragraph_index": p_idx
                            },
                            protected_tokens=token_map,
                            context_hint=f"Slide {slide_idx + 1} Speaker Notes",
                            formatting_meta={"is_speaker_notes": True}
                        ))
                        segment_index += 1

        metadata = {
            "unit_count": len(prs.slides),
            "unit_label": "slides",
            "slide_count": len(prs.slides),
            "total_segments": len(segments)
        }
        return segments, metadata
