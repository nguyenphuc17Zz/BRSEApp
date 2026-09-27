from pathlib import Path
from typing import Dict, Any, Optional, Callable
import asyncio
import re
import json
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment
from app.core.logging import logger
from app.documents.ocr.image_translator import image_translator
from app.documents.parsers.formula_helper import extract_formula_strings, replace_formula_strings

class XlsxRenderer:
    """Renders translated text into Excel (.xlsx) workbook, translating formula strings and inpainting embedded images."""

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
        wb = openpyxl.load_workbook(str(working_path), data_only=False)
        opts = options or {}
        selected_sheets = opts.get("selected_sheets")
        translate_images = opts.get("translate_images", False)
        ocr_mode = opts.get("ocr_mode", "paddleocr")

        total_images = 0
        if translate_images:
            for sname in wb.sheetnames:
                if selected_sheets and sname not in selected_sheets:
                    continue
                s_ws = wb[sname]
                if hasattr(s_ws, "_images") and s_ws._images:
                    total_images += len(s_ws._images)

        processed_img_count = 0

        for sheet_name in wb.sheetnames:
            if selected_sheets and sheet_name not in selected_sheets:
                continue

            ws = wb[sheet_name]
            col_max_lens: Dict[int, int] = {}
            row_max_lines: Dict[int, int] = {}
            is_vi = (tgt_lang or "").lower() in ("vi", "vietnamese", "viet")
            cjk_font_indicators = ("gothic", "mincho", "meiryo", "yu gothic", "simsun", "ms ", "songti")

            # 1. Update text cells and formula string literals
            for row_idx in range(1, ws.max_row + 1):
                for col_idx in range(1, ws.max_column + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    val = cell.value

                    # Handle formula cells: preserve formula structure, translate natural language strings
                    if isinstance(val, str) and val.startswith("="):
                        formula_strings = extract_formula_strings(val)
                        if formula_strings:
                            replacements = {}
                            for item in formula_strings:
                                str_key = f"excel_formula_string_{sheet_name}_{row_idx}_{col_idx}_{item['str_index']}"
                                if str_key in segments_by_loc:
                                    replacements[item["str_index"]] = segments_by_loc[str_key]
                            if replacements:
                                new_val = replace_formula_strings(val, replacements)
                                cell.value = new_val
                        continue

                    # Handle regular text cells
                    loc_key = f"excel_cell_{sheet_name}_{row_idx}_{col_idx}"
                    if loc_key in segments_by_loc:
                        cell.value = segments_by_loc[loc_key]

                    # Auto-wrap and CJK font normalization for text cells
                    if cell.value is not None and isinstance(cell.value, str):
                        s_val = cell.value
                        lines = s_val.split("\n")
                        m_len = max((len(l) for l in lines), default=0)
                        col_max_lens[col_idx] = max(col_max_lens.get(col_idx, 0), m_len)

                        # Wrap text if multi-line or long
                        if "\n" in s_val or len(s_val) > 35:
                            from copy import copy
                            if cell.alignment:
                                al = copy(cell.alignment)
                                al.wrap_text = True
                                cell.alignment = al
                            else:
                                cell.alignment = Alignment(wrap_text=True)

                        # Estimate visual line count for vertical row height auto-fit
                        col_let = get_column_letter(col_idx)
                        c_dim = ws.column_dimensions.get(col_let)
                        c_width = c_dim.width if c_dim and c_dim.width else 10.0
                        chars_per_line = max(6, int(c_width * 0.95))
                        visual_lines = sum(max(1, (len(l) + chars_per_line - 1) // chars_per_line) for l in lines)
                        if visual_lines > 1:
                            row_max_lines[row_idx] = max(row_max_lines.get(row_idx, 1), visual_lines)

                        # Graceful font fallback if CJK-only font is detected
                        if is_vi and cell.font and cell.font.name:
                            if any(k in cell.font.name.lower() for k in cjk_font_indicators):
                                from copy import copy
                                ft = copy(cell.font)
                                ft.name = "Calibri"
                                cell.font = ft

            # Auto-adjust column dimensions to prevent clipped text and ### display
            for col_idx, max_len in col_max_lens.items():
                try:
                    col_letter = get_column_letter(col_idx)
                    dim = ws.column_dimensions.get(col_letter)
                    curr_w = dim.width if dim and dim.width else 10.0
                    target_w = min(55.0, max(float(curr_w), float(max_len + 3)))
                    if target_w > curr_w:
                        ws.column_dimensions[col_letter].width = round(target_w, 1)
                except Exception as col_err:
                    logger.debug(f"Column resize notice for col {col_idx}: {col_err}")

            # Auto-adjust row heights for multi-line and wrapped text cells to prevent clipping
            for r_idx, num_lines in row_max_lines.items():
                try:
                    curr_h = ws.row_dimensions[r_idx].height or 15.0
                    needed_h = max(curr_h, num_lines * 16.5)
                    if needed_h > curr_h:
                        ws.row_dimensions[r_idx].height = round(min(250.0, needed_h), 1)
                except Exception as row_err:
                    logger.debug(f"Row resize notice for row {r_idx}: {row_err}")

            # Auto-adjust merged cell heights: balance multi-row merged ranges to avoid squashed layout
            try:
                if hasattr(ws, "merged_cells") and ws.merged_cells:
                    for rng in list(ws.merged_cells.ranges):
                        if rng.max_row > rng.min_row and rng.min_row in row_max_lines:
                            num_lines = row_max_lines[rng.min_row]
                            needed_total = num_lines * 16.5
                            row_span = rng.max_row - rng.min_row + 1
                            curr_total = sum(ws.row_dimensions[r].height or 15.0 for r in range(rng.min_row, rng.max_row + 1))
                            if needed_total > curr_total:
                                extra_per_row = (needed_total - curr_total) / float(row_span)
                                for r in range(rng.min_row, rng.max_row + 1):
                                    ch = ws.row_dimensions[r].height or 15.0
                                    ws.row_dimensions[r].height = round(min(200.0, ch + extra_per_row), 1)
            except Exception as mrg_err:
                logger.debug(f"Merged cell row resize notice: {mrg_err}")

            # 2. Process embedded images in this worksheet
            if translate_images and hasattr(ws, "_images") and ws._images:
                logger.info(f"Processing {len(ws._images)} embedded images in sheet '{sheet_name}' (OCR Engine: {ocr_mode})...")
                for img_idx, img in enumerate(ws._images):
                    processed_img_count += 1
                    if on_progress:
                        try:
                            if asyncio.iscoroutinefunction(on_progress):
                                await on_progress(f"Đang dịch hình ảnh bảng tính ({processed_img_count}/{total_images})...")
                            else:
                                res = on_progress(f"Đang dịch hình ảnh bảng tính ({processed_img_count}/{total_images})...")
                                if asyncio.iscoroutine(res):
                                    await res
                        except Exception:
                            pass
                    try:
                        raw_bytes = img._data() if hasattr(img, "_data") and callable(img._data) else None
                        if raw_bytes:
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
                                logger.warning(f"Timeout (25s) translating image in sheet '{sheet_name}', skipping.")
                                continue
                            if new_bytes and len(new_bytes) > 0:
                                img._data = lambda nb=new_bytes: nb
                                try:
                                    import io
                                    from PIL import Image as PILImage
                                    img.ref = PILImage.open(io.BytesIO(new_bytes))
                                except Exception:
                                    pass
                    except Exception as img_err:
                        logger.warning(f"Failed to translate embedded image {img_idx + 1} in sheet '{sheet_name}': {img_err}")

        # 3. Rename sheets if translate_sheet_names is enabled
        translate_sheet_names = opts.get("translate_sheet_names", True)
        if translate_sheet_names and wb.sheetnames:
            sheet_title_map = {}
            if provider:
                items = [{"id": i, "text": name} for i, name in enumerate(wb.sheetnames)]
                prompt = f"""Translate the following Excel sheet names from {src_lang} to {tgt_lang}. Keep them concise (max 30 chars).
JSON:
{json.dumps(items, ensure_ascii=False)}

Schema: {{"translations": [{{"id": 0, "translated": "..."}}]}}"""
                try:
                    from app.engine.pipeline import clean_json_response
                    resp = await provider.generate(
                        prompt=prompt,
                        system_instruction=f"Translate spreadsheet tab names concisely from {src_lang} to {tgt_lang}.",
                        temperature=0.1,
                        json_mode=True
                    )
                    data = clean_json_response(resp.text)
                    for t in data.get("translations", []):
                        raw_id = t.get("id")
                        val = t.get("translated", "")
                        if val:
                            sheet_title_map[raw_id] = val
                            try:
                                sheet_title_map[int(raw_id)] = val
                                sheet_title_map[str(raw_id)] = val
                            except (ValueError, TypeError):
                                pass
                except Exception as sheet_err:
                    logger.warning(f"Failed to translate Excel sheet names via AI: {sheet_err}")

            used_names = set()
            for idx, old_name in enumerate(list(wb.sheetnames)):
                new_title = sheet_title_map.get(idx) or sheet_title_map.get(str(idx))
                if new_title and new_title.strip():
                    clean_name = re.sub(r'[\\/?*\[\]:]', '_', new_title.strip())[:31]
                    final_name = clean_name
                    counter = 1
                    while final_name in used_names or (final_name in wb.sheetnames and final_name != old_name):
                        suffix = f"_{counter}"
                        final_name = f"{clean_name[:31-len(suffix)]}{suffix}"
                        counter += 1
                    try:
                        wb[old_name].title = final_name
                        used_names.add(final_name)
                    except Exception as ren_err:
                        logger.warning(f"Could not rename Excel sheet '{old_name}' to '{final_name}': {ren_err}")
                else:
                    used_names.add(old_name)

        wb.save(str(output_path))
        logger.info(f"XLSX workbook successfully rendered to {output_path}")
