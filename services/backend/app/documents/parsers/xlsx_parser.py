from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import openpyxl
from app.documents.parsers.base import DocumentParser
from app.documents.segmenter import ParsedSegment, TokenProtector
from app.documents.parsers.formula_helper import extract_formula_strings

class XlsxParser(DocumentParser):
    """Parses Excel (.xlsx) workbooks, preserving formulas, numbers, and merged cell structures."""

    def parse(self, file_path: Path, options: Optional[Dict[str, Any]] = None) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        # Load workbook with data_only=False so formulas are read as raw formulas (e.g. =SUM(A1:A10))
        wb = openpyxl.load_workbook(str(file_path), data_only=False)
        opts = options or {}
        selected_sheets = opts.get("selected_sheets") # List[str] or None

        segments: List[ParsedSegment] = []
        segment_index = 0
        all_sheet_names = wb.sheetnames
        processed_sheets = []

        for sheet_name in all_sheet_names:
            if selected_sheets and sheet_name not in selected_sheets:
                continue

            processed_sheets.append(sheet_name)
            ws = wb[sheet_name]

            # Track column headers from row 1 if present
            col_headers = {}
            for col_idx in range(1, ws.max_column + 1):
                val = ws.cell(row=1, column=col_idx).value
                if val and isinstance(val, str) and not val.startswith("="):
                    col_headers[col_idx] = val.strip()

            for row_idx in range(1, ws.max_row + 1):
                for col_idx in range(1, ws.max_column + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    val = cell.value

                    if val is None:
                        continue

                    # Smart formula string extraction: keep formula structure, extract natural language strings
                    if isinstance(val, str) and val.startswith("="):
                        formula_strings = extract_formula_strings(val)
                        header_hint = col_headers.get(col_idx, f"Col {col_idx}")
                        for item in formula_strings:
                            str_text = item["text"]
                            protected_text, token_map = TokenProtector.protect_tokens(str_text)
                            segments.append(ParsedSegment(
                                segment_index=segment_index,
                                source_text=protected_text,
                                location={
                                    "type": "excel_formula_string",
                                    "sheet": sheet_name,
                                    "row": row_idx,
                                    "column": col_idx,
                                    "str_index": item["str_index"],
                                    "coordinate": cell.coordinate
                                },
                                protected_tokens=token_map,
                                context_hint=f"Sheet '{sheet_name}'!{cell.coordinate} (Công thức: {header_hint})",
                                formatting_meta={"coordinate": cell.coordinate, "is_formula": True}
                            ))
                            segment_index += 1
                        continue

                    # Skip pure numbers, dates, booleans
                    if not isinstance(val, str):
                        continue

                    text = val.strip()
                    if not text:
                        continue

                    # If text is purely numeric or date string, skip
                    if text.replace(".", "", 1).isdigit():
                        continue

                    protected_text, token_map = TokenProtector.protect_tokens(text)
                    header_hint = col_headers.get(col_idx, f"Col {col_idx}")

                    segments.append(ParsedSegment(
                        segment_index=segment_index,
                        source_text=protected_text,
                        location={
                            "type": "excel_cell",
                            "sheet": sheet_name,
                            "row": row_idx,
                            "column": col_idx,
                            "coordinate": cell.coordinate
                        },
                        protected_tokens=token_map,
                        context_hint=f"Sheet '{sheet_name}' - Header: {header_hint}",
                        formatting_meta={"coordinate": cell.coordinate}
                    ))
                    segment_index += 1

        metadata = {
            "unit_count": len(processed_sheets),
            "unit_label": "sheets",
            "sheets": all_sheet_names,
            "processed_sheets": processed_sheets,
            "total_segments": len(segments)
        }
        return segments, metadata
