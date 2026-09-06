from typing import Dict, List, Any, Optional, Tuple
import re
import httpx
from app.core.logging import logger
from app.documents.segmenter import TokenProtector, ParsedSegment

SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

class GoogleSheetsService:
    """Manages Google Sheets cell classification, formula protection (=...), and range translation via real Google Sheets API."""

    @classmethod
    async def get_spreadsheet(cls, access_token: str, spreadsheet_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Fetches spreadsheet metadata and cell contents."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.get(
                f"{SHEETS_API_BASE}/{spreadsheet_id}?includeGridData=true",
                headers=headers
            )
            if resp.status_code != 200:
                logger.error(f"Failed to fetch Google Sheet: {resp.text}")
                raise ValueError(f"Failed to fetch Google Sheet: {resp.text}")
            return resp.json()

    @classmethod
    def parse_segments(
        cls,
        spreadsheet_data: Dict[str, Any],
        selected_sheets: Optional[List[str]] = None
    ) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        """Extracts translatable text while strictly preserving formulas (=SUM, =VLOOKUP)."""
        segments: List[ParsedSegment] = []
        sheets = spreadsheet_data.get("sheets", [])
        total_cells = 0
        formula_cells_protected = 0

        segment_idx = 0
        for s in sheets:
            sheet_title = s.get("properties", {}).get("title", "Sheet")
            if selected_sheets and sheet_title not in selected_sheets:
                continue

            data_blocks = s.get("data", [])
            for block in data_blocks:
                row_data = block.get("rowData", [])
                for r_idx, row in enumerate(row_data):
                    values = row.get("values", [])
                    for c_idx, cell in enumerate(values):
                        total_cells += 1
                        user_entered = cell.get("userEnteredValue", {})

                        # Formula preservation
                        if "formulaValue" in user_entered or str(user_entered.get("stringValue", "")).startswith("="):
                            formula_cells_protected += 1
                            continue

                        str_val = user_entered.get("stringValue", "").strip()
                        if not str_val or str_val.isdigit() or re.match(r"^[-+]?[0-9]*\.?[0-9]+$", str_val):
                            continue

                        protected_text, tags = TokenProtector.protect(str_val)

                        col_letter = chr(65 + (c_idx % 26))
                        cell_ref = f"{col_letter}{r_idx + 1}"

                        segments.append(ParsedSegment(
                            segment_index=segment_idx,
                            source_text=protected_text,
                            location={"type": "gsheet_cell", "sheet": sheet_title, "row": r_idx, "col": c_idx, "cell_ref": cell_ref},
                            protected_tokens=tags,
                            context_hint=f"Sheet: {sheet_title}",
                            formatting_meta={}
                        ))
                        segment_idx += 1

        metadata = {
            "title": spreadsheet_data.get("properties", {}).get("title", "Spreadsheet"),
            "total_cells": total_cells,
            "formula_cells_protected": formula_cells_protected,
            "total_segments": len(segments)
        }
        return segments, metadata

    @classmethod
    async def get_metadata(
        cls,
        access_token: str,
        spreadsheet_id: str,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Returns sheet tabs and segment count for frontend configuration."""
        data = await cls.get_spreadsheet(access_token, spreadsheet_id, is_mock=is_mock)
        sheet_names = [s.get("properties", {}).get("title", "Sheet") for s in data.get("sheets", [])]
        segments, meta = cls.parse_segments(data)
        return {
            "title": meta.get("title", "Google Sheet"),
            "format": "gsheet",
            "sheet_names": sheet_names,
            "total_cells": meta.get("total_cells", 0),
            "formula_cells_protected": meta.get("formula_cells_protected", 0),
            "total_segments": len(segments)
        }

    @classmethod
    async def apply_translations_to_copy(
        cls,
        access_token: str,
        copy_spreadsheet_id: str,
        updates: List[Dict[str, Any]],
        is_mock: bool = False
    ):
        """Writes translated values back to cells in the non-destructive copy."""
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        data_payload = []
        for u in updates:
            data_payload.append({
                "range": f"'{u['sheet']}'!R{u['row'] + 1}C{u['col'] + 1}",
                "values": [[u["translated_text"]]]
            })

        body = {
            "valueInputOption": "USER_ENTERED",
            "data": data_payload
        }

        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(
                f"{SHEETS_API_BASE}/{copy_spreadsheet_id}/values:batchUpdate",
                headers=headers,
                json=body
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to batch update Google Sheet: {resp.text}")
