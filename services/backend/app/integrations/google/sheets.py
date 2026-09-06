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
        if is_mock:
            return {
                "properties": {"title": "Mock Spreadsheet"},
                "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1"}, "data": []}]
            }

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
        if is_mock:
            return

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

    @classmethod
    async def update_sheet_titles(
        cls,
        access_token: str,
        copy_spreadsheet_id: str,
        sheet_title_updates: List[Dict[str, Any]],
        is_mock: bool = False
    ):
        """Updates sheet titles on Google Sheets tab bar using updateSheetProperties."""
        if is_mock or not sheet_title_updates:
            return

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        requests = []
        for item in sheet_title_updates:
            sid = item.get("sheet_id")
            title = (item.get("title") or "").strip()
            # Clean invalid Excel/Sheets characters and truncate to 31 chars
            title = re.sub(r'[\\/?*\[\]:]', '_', title)[:31]
            if sid is not None and title:
                requests.append({
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sid,
                            "title": title
                        },
                        "fields": "title"
                    }
                })

        if requests:
            async with httpx.AsyncClient(timeout=25.0) as http:
                resp = await http.post(
                    f"{SHEETS_API_BASE}/{copy_spreadsheet_id}:batchUpdate",
                    headers=headers,
                    json={"requests": requests}
                )
                if resp.status_code != 200:
                    logger.warning(f"Failed to update sheet titles on Google Sheet {copy_spreadsheet_id}: {resp.text}")
                else:
                    logger.info(f"Successfully updated {len(requests)} sheet titles on Google Sheet {copy_spreadsheet_id}.")

    @classmethod
    async def translate_and_update_sheet_titles(
        cls,
        access_token: str,
        copy_spreadsheet_id: str,
        source_lang: str = "ja",
        target_lang: str = "vi",
        provider: Any = None,
        model: Optional[str] = None,
        is_mock: bool = False
    ):
        """Translates sheet names and updates them on Google Sheets tab bar."""
        if is_mock:
            return

        import json
        from app.engine.pipeline import clean_json_response

        data = await cls.get_spreadsheet(access_token, copy_spreadsheet_id, is_mock=is_mock)
        sheets = data.get("sheets", [])
        if not sheets:
            return

        titles_to_translate = []
        for s in sheets:
            props = s.get("properties", {})
            sid = props.get("sheetId")
            title = (props.get("title") or "").strip()
            if sid is not None and title:
                titles_to_translate.append({"sheet_id": sid, "title": title})

        if not titles_to_translate:
            return

        from app.integrations.google.docs import apply_smart_title_fallback

        updates = []
        providers_to_try = []
        if provider:
            providers_to_try.append((provider, model))
        try:
            from app.providers.registry import provider_registry
            gemini_prov = provider_registry.get_provider("gemini")
            if gemini_prov and gemini_prov != provider:
                providers_to_try.append((gemini_prov, "gemini-2.5-flash"))
        except Exception:
            pass

        items_payload = [{"id": i, "text": item["title"]} for i, item in enumerate(titles_to_translate)]
        prompt = f"""Translate the following spreadsheet sheet/tab names from {source_lang} to {target_lang}. Keep them concise (max 30 characters) suitable for spreadsheet tabs.
JSON input:
{json.dumps(items_payload, ensure_ascii=False)}

Return JSON matching:
{{"translations": [{{"id": 0, "translated": "..."}}]}}"""

        for current_prov, current_mod in providers_to_try:
            try:
                resp_data = await current_prov.generate(
                    prompt=prompt,
                    system_instruction=f"You are a professional translator from {source_lang} to {target_lang}. Translate spreadsheet sheet names concisely.",
                    model=current_mod,
                    temperature=0.1,
                    json_mode=True
                )
                parsed = clean_json_response(resp_data.text)
                trans_list = parsed.get("translations", [])
                trans_map = {}
                for item in trans_list:
                    if "id" in item:
                        trans_map[item["id"]] = item.get("translated", "")
                        trans_map[str(item["id"])] = item.get("translated", "")

                for i, item in enumerate(titles_to_translate):
                    trans_val = trans_map.get(i) or trans_map.get(str(i))
                    if trans_val and trans_val.strip():
                        updates.append({
                            "sheet_id": item["sheet_id"],
                            "title": trans_val.strip()
                        })
                if updates:
                    break
            except Exception as e:
                logger.warning(f"Failed to translate sheet names with provider {getattr(current_prov, 'name', current_prov)}: {e}")

        # Smart fallback if updates is empty
        if not updates:
            for item in titles_to_translate:
                fallback_title = apply_smart_title_fallback(item["title"], source_lang, target_lang)
                updates.append({"sheet_id": item["sheet_id"], "title": fallback_title})

        await cls.update_sheet_titles(access_token, copy_spreadsheet_id, updates, is_mock=is_mock)

