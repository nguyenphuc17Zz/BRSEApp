from typing import Dict, List, Any, Optional, Tuple
import json
import re
import httpx
from app.core.logging import logger
from app.documents.segmenter import TokenProtector, ParsedSegment
from app.integrations.google.sheets_ast_sync import (
    CellType,
    SheetTab,
    RowBlock,
    CellBlock,
    GoogleSheetsGridParser,
    SheetMatrixMyersDiffEngine,
    SheetReverseIndexBatchPlanner,
    SheetDiffOpType,
    SheetDiffOperation,
    col_index_to_letter,
)

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
                start_row = block.get("startRow", 0)
                row_data = block.get("rowData", [])
                for r_offset, row in enumerate(row_data):
                    actual_r_idx = start_row + r_offset
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

                        col_letter = col_index_to_letter(c_idx)
                        cell_ref = f"{col_letter}{actual_r_idx + 1}"

                        segments.append(ParsedSegment(
                            segment_index=segment_idx,
                            source_text=protected_text,
                            location={"type": "gsheet_cell", "sheet": sheet_title, "row": actual_r_idx, "col": c_idx, "cell_ref": cell_ref},
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
        """Writes translated values back to cells in the non-destructive copy using contiguous range aggregation."""
        if is_mock or not updates:
            return

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # Optimize cell updates into contiguous rectangular ValueRanges
        cell_updates_mapped = [{
            "sheet": u.get("sheet", "Sheet1"),
            "row": u.get("row", 0),
            "col": u.get("col", 0),
            "new_value": u.get("translated_text", u.get("new_value", ""))
        } for u in updates]
        data_payload = SheetReverseIndexBatchPlanner._aggregate_contiguous_ranges(cell_updates_mapped)

        if not data_payload:
            for u in updates:
                text_val = u.get("translated_text", u.get("new_value", ""))
                data_payload.append({
                    "range": f"'{u.get('sheet', 'Sheet1')}'!R{u.get('row', 0) + 1}C{u.get('col', 0) + 1}",
                    "values": [[text_val]]
                })

        for i in range(0, len(data_payload), 100):
            chunk = data_payload[i:i + 100]
            body = {
                "valueInputOption": "USER_ENTERED",
                "data": chunk
            }
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{SHEETS_API_BASE}/{copy_spreadsheet_id}/values:batchUpdate",
                    headers=headers,
                    json=body
                )
                if resp.status_code != 200:
                    logger.warning(f"Failed to batch update Google Sheet {copy_spreadsheet_id}: {resp.text}")

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

    @classmethod
    async def apply_smart_matrix_sync_to_existing_sheet(
        cls,
        access_token: str,
        target_spreadsheet_id: str,
        segments: List[Any],
        previous_segments: Optional[List[Any]] = None,
        source_spreadsheet_id: Optional[str] = None,
        selected_sheets: Optional[List[str]] = None,
        parent_folder_id: Optional[str] = None,
        source_lang: str = "ja",
        target_lang: str = "vi",
        ocr_engine: str = "paddleocr",
        translate_images: bool = True,
        provider: Any = None,
        is_mock: bool = False,
    ):
        """SOTA 2D Semantic Matrix Myers Diff & Reverse-Index Dimension Sync for Google Sheets:
        1. Parses source and target spreadsheet grids into rich 2D SheetTab models with formula protection.
        2. Computes hierarchical Myers diff across tabs and rows (detecting ADD_SHEET, DELETE_SHEET, INSERT_ROWS, DELETE_ROWS, UPDATE_CELLS).
        3. ReverseIndexBatchPlanner orders dimension mutations descending to eliminate row drift.
        4. Aggregates cell updates into contiguous ValueRanges to maximize throughput within API quota.
        5. Executes batchUpdate for structure and values:batchUpdate for cell values without destructive XLSX export.
        """
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # 1. Fetch target spreadsheet data
        target_data = await cls.get_spreadsheet(access_token, target_spreadsheet_id, is_mock=is_mock)
        target_tabs = GoogleSheetsGridParser.parse_spreadsheet(target_data, selected_sheets=selected_sheets)

        # 2. Fetch or build source spreadsheet data
        source_tabs: List[SheetTab] = []
        if source_spreadsheet_id:
            try:
                source_data = await cls.get_spreadsheet(access_token, source_spreadsheet_id, is_mock=is_mock)
                source_tabs = GoogleSheetsGridParser.parse_spreadsheet(source_data, selected_sheets=selected_sheets)
            except Exception as src_err:
                logger.warning(f"Could not parse source spreadsheet grid ({source_spreadsheet_id}): {src_err}")

        # If source_tabs could not be fetched from API, construct synthetic SheetTabs from segments
        if not source_tabs and segments:
            by_sheet_segs: Dict[str, List[Any]] = {}
            for seg in segments:
                loc = json.loads(getattr(seg, "location_json", "{}") or "{}")
                sh = loc.get("sheet", "Sheet1")
                by_sheet_segs.setdefault(sh, []).append(seg)

            for sh_idx, (sh_title, sh_list) in enumerate(by_sheet_segs.items()):
                tab = SheetTab(
                    sheet_id=sh_idx,
                    title=sh_title,
                    index=sh_idx,
                    row_count=1000,
                    col_count=26,
                )
                by_row_dict: Dict[int, List[CellBlock]] = {}
                for seg in sh_list:
                    loc = json.loads(getattr(seg, "location_json", "{}") or "{}")
                    r = loc.get("row", 0)
                    c = loc.get("col", 0)
                    token_map = json.loads(getattr(seg, "protected_tokens_json", "{}") or "{}")
                    raw_src, _ = TokenProtector.restore_tokens(getattr(seg, "source_text", "") or "", token_map)
                    cb = CellBlock(
                        row_idx=r,
                        col_idx=c,
                        cell_ref=loc.get("cell_ref", f"R{r+1}C{c+1}"),
                        raw_value=raw_src,
                        string_value=raw_src.strip(),
                        cell_type=CellType.TEXT if raw_src.strip() else CellType.EMPTY,
                    )
                    by_row_dict.setdefault(r, []).append(cb)
                    tab.cells_by_coord[(r, c)] = cb

                for r_idx in sorted(by_row_dict.keys()):
                    r_cells = by_row_dict[r_idx]
                    anchor_key, fp = GoogleSheetsGridParser._compute_row_signature(sh_title, r_idx, r_cells)
                    tab.rows.append(RowBlock(
                        sheet_id=sh_idx,
                        sheet_title=sh_title,
                        row_idx=r_idx,
                        cells=r_cells,
                        anchor_key=anchor_key,
                        fingerprint=fp,
                    ))
                source_tabs.append(tab)

        # 3. Compute 2D Semantic Matrix Myers Diff
        diff_engine = SheetMatrixMyersDiffEngine(similarity_threshold=0.50)
        diff_ops = diff_engine.compute_diff(
            source_tabs=source_tabs,
            target_tabs=target_tabs,
            current_segments=segments,
            previous_segments=previous_segments,
            selected_sheets=selected_sheets,
        )

        # 4. Plan reverse-index dimension changes & contiguous range updates
        structural_requests, value_ranges = SheetReverseIndexBatchPlanner.plan_batch_updates(diff_ops)

        # 5. Execute structural batchUpdate (addSheet, deleteSheet, deleteDimension, insertDimension)
        if structural_requests and not is_mock:
            for i in range(0, len(structural_requests), 50):
                chunk = structural_requests[i:i + 50]
                async with httpx.AsyncClient(timeout=30.0) as http:
                    resp = await http.post(
                        f"{SHEETS_API_BASE}/{target_spreadsheet_id}:batchUpdate",
                        headers=headers,
                        json={"requests": chunk}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"Failed to apply structural batch mutations in Google Sheet {target_spreadsheet_id}: {resp.text}")
                    else:
                        logger.info(f"Successfully applied {len(chunk)} structural mutations to Google Sheet {target_spreadsheet_id}.")

        # 6. Process in-cell =IMAGE formulas if translate_images is True and not is_mock
        image_formula_updates: List[Dict[str, Any]] = []
        if translate_images and not is_mock:
            image_cells_to_process: List[Tuple[str, CellBlock]] = []
            for s_tab in source_tabs:
                for s_row in s_tab.rows:
                    for s_cell in s_row.cells:
                        if s_cell.is_image_formula and s_cell.image_url:
                            image_cells_to_process.append((s_tab.title, s_cell))

            if image_cells_to_process:
                from app.documents.ocr.image_translator import image_translator
                from app.integrations.google.drive import GoogleDriveService
                import uuid

                async with httpx.AsyncClient(timeout=45.0) as http:
                    for sh_title, img_cell in image_cells_to_process:
                        orig_url = img_cell.image_url
                        try:
                            img_res = await http.get(orig_url)
                            if img_res.status_code == 200 and len(img_res.content) > 20:
                                orig_bytes = img_res.content
                                trans_bytes = await image_translator.process_image(
                                    image_bytes=orig_bytes,
                                    src_lang=source_lang,
                                    tgt_lang=target_lang,
                                    ocr_engine=ocr_engine,
                                    provider=provider
                                )
                                # Only upload if text was found and translated; otherwise keep original URL intact
                                if trans_bytes and trans_bytes != orig_bytes:
                                    temp_fn = f"translated_sheet_img_{uuid.uuid4().hex[:8]}.png"
                                    upload_res = await GoogleDriveService.upload_file(
                                        access_token=access_token,
                                        filename=temp_fn,
                                        content_bytes=trans_bytes,
                                        mime_type="image/png",
                                        parent_folder_id=parent_folder_id
                                    )
                                    temp_fid = upload_res.get("id")
                                    if temp_fid:
                                        perm_res = await http.post(
                                            f"https://www.googleapis.com/drive/v3/files/{temp_fid}/permissions?supportsAllDrives=true",
                                            headers=headers,
                                            json={"role": "reader", "type": "anyone"}
                                        )
                                        if perm_res.status_code in (200, 201):
                                            public_url = f"https://lh3.googleusercontent.com/d/{temp_fid}"
                                            extra = f", {img_cell.image_formula_args}" if img_cell.image_formula_args else ""
                                            new_formula = f'=IMAGE("{public_url}"{extra})'
                                            image_formula_updates.append({
                                                "sheet": sh_title,
                                                "row": img_cell.row_idx,
                                                "col": img_cell.col_idx,
                                                "translated_text": new_formula,
                                                "new_value": new_formula
                                            })
                                            logger.info(f"Successfully translated in-cell image at {sh_title}!R{img_cell.row_idx+1}C{img_cell.col_idx+1} -> {public_url}")
                        except Exception as img_err:
                            logger.warning(f"Could not translate in-cell image at {orig_url}: {img_err}")

        # 7. Execute cell updates via apply_translations_to_copy
        all_cell_updates: List[Dict[str, Any]] = []
        for op in diff_ops:
            if op.op_type == SheetDiffOpType.UPDATE_CELLS:
                all_cell_updates.extend(op.cell_updates)

        if image_formula_updates:
            all_cell_updates.extend(image_formula_updates)

        formatted_updates = [{
            "sheet": u["sheet"],
            "row": u["row"],
            "col": u["col"],
            "translated_text": u.get("new_value", u.get("translated_text", ""))
        } for u in all_cell_updates] if all_cell_updates else [{
            "sheet": json.loads(getattr(s, "location_json", "{}") or "{}").get("sheet", "Sheet1"),
            "row": json.loads(getattr(s, "location_json", "{}") or "{}").get("row", 0),
            "col": json.loads(getattr(s, "location_json", "{}") or "{}").get("col", 0),
            "translated_text": getattr(s, "translated_text", "") or getattr(s, "source_text", "")
        } for s in segments if getattr(s, "translated_text", None)]

        await cls.apply_translations_to_copy(
            access_token=access_token,
            copy_spreadsheet_id=target_spreadsheet_id,
            updates=formatted_updates,
            is_mock=is_mock
        )


