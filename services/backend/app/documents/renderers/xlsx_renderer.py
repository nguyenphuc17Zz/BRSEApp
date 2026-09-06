from pathlib import Path
from typing import Dict, Any, Optional
import openpyxl
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
        provider: Any = None
    ):
        wb = openpyxl.load_workbook(str(working_path), data_only=False)
        opts = options or {}
        translate_images = opts.get("translate_images", False)
        ocr_mode = opts.get("ocr_mode", "paddleocr")

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
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

            # 2. Process embedded images in this worksheet
            if translate_images and hasattr(ws, "_images") and ws._images:
                logger.info(f"Processing {len(ws._images)} embedded images in sheet '{sheet_name}' (OCR Engine: {ocr_mode})...")
                for img_idx, img in enumerate(ws._images):
                    try:
                        raw_bytes = img._data() if hasattr(img, "_data") and callable(img._data) else None
                        if raw_bytes:
                            new_bytes = await image_translator.process_image(
                                image_bytes=raw_bytes,
                                src_lang=src_lang,
                                tgt_lang=tgt_lang,
                                ocr_engine=ocr_mode,
                                provider=provider
                            )
                            if new_bytes and len(new_bytes) > 0:
                                img._data = lambda nb=new_bytes: nb
                    except Exception as img_err:
                        logger.warning(f"Failed to translate embedded image {img_idx + 1} in sheet '{sheet_name}': {img_err}")

        wb.save(str(output_path))
        logger.info(f"XLSX workbook successfully rendered to {output_path}")
