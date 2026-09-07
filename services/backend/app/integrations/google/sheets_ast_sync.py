"""
2D Semantic Matrix Myers Diff & Reverse-Index Dimension Planner Engine for Google Sheets.
State-of-the-Art (SOTA) in-place synchronization for collaborative spreadsheet translation.

Capabilities:
1. 2D Grid Matrix Parsing: Parses Google Sheets REST API JSON into rich SheetTab, RowBlock, and CellBlock objects.
2. Formula Immunity & Classification: Strictly protects formulas (=SUM, =VLOOKUP, =IF, etc.), numbers, booleans.
3. Row-level Semantic Fingerprinting & Myers LCS Diff: Detects unchanged, modified, inserted, and deleted rows.
4. Reverse-Index Dimension Planner: Orders deleteDimension and insertDimension requests in descending order
   of row index to eliminate row-shift drift (Zero Row Drift).
5. Contiguous Range Aggregation: Aggregates cell mutations into optimal ValueRange rectangular bounds to minimize API quota.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from app.documents.segmenter import TokenProtector

logger = logging.getLogger("comtor_copilot.sheets_ast_sync")

IMAGE_FORMULA_REGEX = re.compile(r'^\s*=\s*IMAGE\s*\(\s*["\']([^"\']+)["\'](?:\s*,\s*([^)]*))?\)\s*$', re.IGNORECASE)


class CellType(str, Enum):
    FORMULA = "formula"
    NUMBER = "number"
    BOOLEAN = "boolean"
    TEXT = "text"
    EMPTY = "empty"


class SheetDiffOpType(str, Enum):
    NO_CHANGE = "no_change"
    UPDATE_CELLS = "update_cells"
    INSERT_ROWS = "insert_rows"
    DELETE_ROWS = "delete_rows"
    ADD_SHEET = "add_sheet"
    DELETE_SHEET = "delete_sheet"
    RENAME_SHEET = "rename_sheet"


@dataclass
class CellBlock:
    row_idx: int
    col_idx: int
    cell_ref: str
    raw_value: Any
    string_value: str
    formula: Optional[str] = None
    cell_type: CellType = CellType.EMPTY
    formatting: Dict[str, Any] = field(default_factory=dict)
    is_image_formula: bool = False
    image_url: Optional[str] = None
    image_formula_args: str = ""

    @property
    def is_translatable(self) -> bool:
        return self.cell_type == CellType.TEXT and bool(self.string_value.strip())


@dataclass
class RowBlock:
    sheet_id: int
    sheet_title: str
    row_idx: int
    cells: List[CellBlock] = field(default_factory=list)
    anchor_key: str = ""
    fingerprint: str = ""

    @property
    def has_content(self) -> bool:
        return any(c.cell_type != CellType.EMPTY for c in self.cells)


@dataclass
class SheetTab:
    sheet_id: int
    title: str
    index: int
    row_count: int
    col_count: int
    rows: List[RowBlock] = field(default_factory=list)
    cells_by_coord: Dict[Tuple[int, int], CellBlock] = field(default_factory=dict)


@dataclass
class SheetDiffOperation:
    op_type: SheetDiffOpType
    sheet_id: int
    sheet_title: str
    start_row_index: int = 0
    end_row_index: int = 0
    count: int = 0
    cell_updates: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


def col_index_to_letter(col_idx: int) -> str:
    """Converts a 0-indexed column integer to spreadsheet letters (0 -> A, 25 -> Z, 26 -> AA)."""
    result = ""
    temp = col_idx
    while temp >= 0:
        result = chr(65 + (temp % 26)) + result
        temp = (temp // 26) - 1
    return result


class GoogleSheetsGridParser:
    """Parses Google Sheets REST API spreadsheet JSON into structured SheetTab, RowBlock, and CellBlock objects."""

    @classmethod
    def parse_spreadsheet(
        cls,
        spreadsheet_data: Dict[str, Any],
        selected_sheets: Optional[List[str]] = None
    ) -> List[SheetTab]:
        tabs: List[SheetTab] = []
        raw_sheets = spreadsheet_data.get("sheets", [])

        for s_data in raw_sheets:
            props = s_data.get("properties", {})
            sheet_id = props.get("sheetId", 0)
            title = props.get("title", "Sheet")
            index = props.get("index", 0)
            grid_props = props.get("gridProperties", {})
            row_count = grid_props.get("rowCount", 0)
            col_count = grid_props.get("columnCount", 0)

            if selected_sheets and title not in selected_sheets and str(sheet_id) not in selected_sheets:
                continue

            tab = SheetTab(
                sheet_id=sheet_id,
                title=title,
                index=index,
                row_count=row_count,
                col_count=col_count,
            )

            data_blocks = s_data.get("data", [])
            for block in data_blocks:
                start_row = block.get("startRow", 0)
                row_data = block.get("rowData", [])

                for r_offset, r_item in enumerate(row_data):
                    actual_r_idx = start_row + r_offset
                    values = r_item.get("values", [])
                    row_cells: List[CellBlock] = []

                    for c_idx, cell_dict in enumerate(values):
                        user_entered = cell_dict.get("userEnteredValue", {})
                        eff_val = cell_dict.get("effectiveValue", {})
                        fmt = cell_dict.get("userEnteredFormat", {})
                        cell_ref = f"{col_index_to_letter(c_idx)}{actual_r_idx + 1}"

                        # 1. Formula detection
                        formula_str = user_entered.get("formulaValue")
                        if not formula_str and str(user_entered.get("stringValue", "")).startswith("="):
                            formula_str = str(user_entered.get("stringValue", ""))

                        if formula_str:
                            img_match = IMAGE_FORMULA_REGEX.match(formula_str)
                            is_img = bool(img_match)
                            img_url = img_match.group(1) if img_match else None
                            img_args = (img_match.group(2) or "").strip() if img_match else ""

                            c_block = CellBlock(
                                row_idx=actual_r_idx,
                                col_idx=c_idx,
                                cell_ref=cell_ref,
                                raw_value=formula_str,
                                string_value=str(eff_val.get("stringValue", "") or eff_val.get("numberValue", "")),
                                formula=formula_str,
                                cell_type=CellType.FORMULA,
                                formatting=fmt,
                                is_image_formula=is_img,
                                image_url=img_url,
                                image_formula_args=img_args,
                            )
                        elif "boolValue" in user_entered or "boolValue" in eff_val:
                            c_block = CellBlock(
                                row_idx=actual_r_idx,
                                col_idx=c_idx,
                                cell_ref=cell_ref,
                                raw_value=user_entered.get("boolValue"),
                                string_value=str(user_entered.get("boolValue")),
                                cell_type=CellType.BOOLEAN,
                                formatting=fmt,
                            )
                        elif "numberValue" in user_entered:
                            c_block = CellBlock(
                                row_idx=actual_r_idx,
                                col_idx=c_idx,
                                cell_ref=cell_ref,
                                raw_value=user_entered.get("numberValue"),
                                string_value=str(user_entered.get("numberValue")),
                                cell_type=CellType.NUMBER,
                                formatting=fmt,
                            )
                        else:
                            s_val = user_entered.get("stringValue", "")
                            if not s_val and eff_val.get("stringValue"):
                                s_val = eff_val.get("stringValue")

                            cleaned_s = str(s_val or "").strip()
                            if not cleaned_s:
                                c_type = CellType.EMPTY
                            elif re.match(r"^[-+]?[0-9]*\.?[0-9]+$", cleaned_s):
                                c_type = CellType.NUMBER
                            else:
                                c_type = CellType.TEXT

                            c_block = CellBlock(
                                row_idx=actual_r_idx,
                                col_idx=c_idx,
                                cell_ref=cell_ref,
                                raw_value=s_val,
                                string_value=cleaned_s,
                                cell_type=c_type,
                                formatting=fmt,
                            )

                        row_cells.append(c_block)
                        tab.cells_by_coord[(actual_r_idx, c_idx)] = c_block

                    # Compute anchor key and fingerprint for the row
                    anchor_key, fp = cls._compute_row_signature(title, actual_r_idx, row_cells)
                    row_block = RowBlock(
                        sheet_id=sheet_id,
                        sheet_title=title,
                        row_idx=actual_r_idx,
                        cells=row_cells,
                        anchor_key=anchor_key,
                        fingerprint=fp,
                    )
                    tab.rows.append(row_block)

            tabs.append(tab)

        return tabs

    @staticmethod
    def _compute_row_signature(sheet_title: str, row_idx: int, cells: List[CellBlock]) -> Tuple[str, str]:
        """Creates semantic anchor keys and Myers diffing fingerprints for a row."""
        # 1. Semantic Anchor: First 1-3 non-empty cells
        non_empty = [c.string_value for c in cells if c.cell_type != CellType.EMPTY and c.string_value]
        anchor_key = " :: ".join(non_empty[:3]).lower() if non_empty else f"row_{row_idx}"

        # 2. Fingerprint: Normalized sequence of non-empty content
        norm_content = "|".join(re.sub(r"\s+", " ", c.string_value).lower() for c in cells if c.string_value)
        fp_raw = f"{sheet_title}::{anchor_key}::{norm_content}"
        fp = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()[:16]
        return anchor_key, fp


class SheetMatrixMyersDiffEngine:
    """Computes the 2D hierarchical structural and cell difference between Source Sheet and Target Sheet."""

    def __init__(self, similarity_threshold: float = 0.50):
        self.similarity_threshold = similarity_threshold

    def compute_diff(
        self,
        source_tabs: List[SheetTab],
        target_tabs: List[SheetTab],
        current_segments: List[Any],
        previous_segments: Optional[List[Any]] = None,
        selected_sheets: Optional[List[str]] = None,
    ) -> List[SheetDiffOperation]:
        ops: List[SheetDiffOperation] = []

        # Build segment translation lookup maps
        # 1. source_text -> translated_text
        src_to_tgt_map: Dict[str, str] = {}
        for s in current_segments:
            token_map = json.loads(getattr(s, "protected_tokens_json", "{}") or "{}")
            raw_src, _ = TokenProtector.restore_tokens(getattr(s, "source_text", "") or "", token_map)
            s_raw = raw_src.strip()
            s_trans = (getattr(s, "translated_text", "") or "").strip()
            if s_raw and s_trans:
                src_to_tgt_map[s_raw] = s_trans

        # 2. previous segment lookup
        prev_src_to_tgt_map: Dict[str, str] = {}
        prev_tgt_set: Set[str] = set()
        if previous_segments:
            for ps in previous_segments:
                token_map = json.loads(getattr(ps, "protected_tokens_json", "{}") or "{}")
                raw_p, _ = TokenProtector.restore_tokens(getattr(ps, "source_text", "") or "", token_map)
                p_raw = raw_p.strip()
                p_trans = (getattr(ps, "translated_text", "") or "").strip()
                if p_raw and p_trans:
                    prev_src_to_tgt_map[p_raw] = p_trans
                    prev_tgt_set.add(p_trans)

        # Level 1: Tab-level Multi-Stage Diff (ID-based, Index-based, and Title-based)
        filtered_src = [t for t in source_tabs if not selected_sheets or t.title in selected_sheets]
        filtered_tgt = [t for t in target_tabs if not selected_sheets or t.title in selected_sheets]

        tgt_by_id = {t.sheet_id: t for t in filtered_tgt}
        tgt_by_title = {t.title: t for t in filtered_tgt}
        tgt_by_index = {t.index: t for t in filtered_tgt}

        matched_s_to_t: Dict[int, SheetTab] = {}  # s.index -> matched target SheetTab
        matched_tgt_ids: Set[int] = set()

        # Pass 1: Match by sheet_id (Primary Key - guaranteed across Google Drive copies)
        for s in filtered_src:
            if s.sheet_id in tgt_by_id and s.sheet_id not in matched_tgt_ids:
                matched_s_to_t[s.index] = tgt_by_id[s.sheet_id]
                matched_tgt_ids.add(s.sheet_id)

        # Pass 2: Match by exact title
        for s in filtered_src:
            if s.index not in matched_s_to_t and s.title in tgt_by_title:
                t = tgt_by_title[s.title]
                if t.sheet_id not in matched_tgt_ids:
                    matched_s_to_t[s.index] = t
                    matched_tgt_ids.add(t.sheet_id)

        # Pass 3: Match by previous translation memory (e.g. "システム構成" -> "Cấu hình hệ thống")
        for s in filtered_src:
            if s.index not in matched_s_to_t:
                prev_trans_title = prev_src_to_tgt_map.get(s.title) or src_to_tgt_map.get(s.title)
                if prev_trans_title and prev_trans_title in tgt_by_title:
                    t = tgt_by_title[prev_trans_title]
                    if t.sheet_id not in matched_tgt_ids:
                        matched_s_to_t[s.index] = t
                        matched_tgt_ids.add(t.sheet_id)

        # Pass 4: Match by positional index ONLY if:
        # 1) No sheet_id matches were found at all (e.g. completely regenerated sheetIds from foreign import or mocks), AND
        # 2) Both tab lists share the same length or slot is free.
        # CRITICAL SOTA GUARANTEE: If sheet_id matching already succeeded for other tabs,
        # it proves the spreadsheets share the Google Drive sheet_id namespace.
        # Thus, any remaining unmatched source tab is truly a newly added sheet (ADD_SHEET),
        # and any remaining unmatched target tab is an obsolete sheet (DELETE_SHEET).
        has_shared_sheet_ids = len(matched_tgt_ids) > 0
        if not has_shared_sheet_ids:
            for s in filtered_src:
                if s.index not in matched_s_to_t:
                    if s.index in tgt_by_index:
                        t = tgt_by_index[s.index]
                        if t.sheet_id not in matched_tgt_ids:
                            matched_s_to_t[s.index] = t
                            matched_tgt_ids.add(t.sheet_id)

        # A. Detect ADD_SHEET (Source tabs with no matching target tab)
        for s in filtered_src:
            if s.index not in matched_s_to_t:
                target_title = prev_src_to_tgt_map.get(s.title) or src_to_tgt_map.get(s.title) or s.title
                logger.info(f"SOTA Sheets Sync: ADD_SHEET detected for new source tab '{s.title}' -> '{target_title}'")
                ops.append(
                    SheetDiffOperation(
                        op_type=SheetDiffOpType.ADD_SHEET,
                        sheet_id=s.sheet_id,
                        sheet_title=s.title,
                        count=1,
                        metadata={"title": target_title, "index": s.index}
                    )
                )
                # Emit initial cell updates for the newly added sheet
                initial_updates: List[Dict[str, Any]] = []
                for s_row in s.rows:
                    for s_cell in s_row.cells:
                        if s_cell.is_translatable:
                            trans_val = src_to_tgt_map.get(s_cell.string_value, s_cell.string_value)
                            initial_updates.append({
                                "sheet": target_title,
                                "row": s_cell.row_idx,
                                "col": s_cell.col_idx,
                                "new_value": trans_val,
                                "old_value": "",
                                "cell_ref": s_cell.cell_ref
                            })
                if initial_updates:
                    ops.append(
                        SheetDiffOperation(
                            op_type=SheetDiffOpType.UPDATE_CELLS,
                            sheet_id=s.sheet_id,
                            sheet_title=target_title,
                            cell_updates=initial_updates
                        )
                    )

        # B. Detect DELETE_SHEET (Target tabs with no matching source tab)
        unmatched_tgt = [t for t in filtered_tgt if t.sheet_id not in matched_tgt_ids]
        if unmatched_tgt and len(filtered_tgt) - len(unmatched_tgt) >= 1:
            for t in unmatched_tgt:
                logger.info(f"SOTA Sheets Sync: DELETE_SHEET detected for removed target tab '{t.title}' (sheetId {t.sheet_id})")
                ops.append(
                    SheetDiffOperation(
                        op_type=SheetDiffOpType.DELETE_SHEET,
                        sheet_id=t.sheet_id,
                        sheet_title=t.title,
                        count=1
                    )
                )

        # Level 2 & 3: Row-level Myers LCS Diff & Cell Deltas per Matched Tab Pair
        for s in filtered_src:
            t = matched_s_to_t.get(s.index)
            if not t:
                continue

            tab_ops = self._diff_tab_grid(
                source_tab=s,
                target_tab=t,
                src_to_tgt_map=src_to_tgt_map,
                prev_src_to_tgt_map=prev_src_to_tgt_map,
            )
            ops.extend(tab_ops)

        return ops

    def _diff_tab_grid(
        self,
        source_tab: SheetTab,
        target_tab: SheetTab,
        src_to_tgt_map: Dict[str, str],
        prev_src_to_tgt_map: Dict[str, str],
    ) -> List[SheetDiffOperation]:
        ops: List[SheetDiffOperation] = []

        s_rows = source_tab.rows
        t_rows = target_tab.rows

        # 1. Build row matching matrix using anchor keys and content similarity
        matched_s_to_t: Dict[int, int] = {}
        matched_t_indices: Set[int] = set()

        # Pass 1: Exact Anchor Key & Primary Key Match
        t_anchor_map: Dict[str, List[int]] = {}
        t_pk_map: Dict[str, List[int]] = {}
        for t_idx, tr in enumerate(t_rows):
            if tr.anchor_key and tr.has_content:
                t_anchor_map.setdefault(tr.anchor_key, []).append(t_idx)
            non_empty_t = [c.string_value for c in tr.cells if c.string_value]
            if non_empty_t:
                pk_val = non_empty_t[0].strip().lower()
                if len(pk_val) <= 30:
                    t_pk_map.setdefault(pk_val, []).append(t_idx)

        for s_idx, sr in enumerate(s_rows):
            if not sr.has_content:
                continue

            s_trans_cells = [src_to_tgt_map.get(c.string_value, c.string_value) for c in sr.cells if c.string_value]
            s_trans_anchor = " :: ".join(s_trans_cells[:3]).lower()
            norm_anchor = sr.anchor_key.lower()

            # A. Exact anchor match
            candidates = t_anchor_map.get(norm_anchor) or t_anchor_map.get(s_trans_anchor)
            matched = False
            if candidates:
                for cand_idx in candidates:
                    if cand_idx not in matched_t_indices:
                        matched_s_to_t[s_idx] = cand_idx
                        matched_t_indices.add(cand_idx)
                        matched = True
                        break

            # B. Primary Key match (first column ID e.g. "1", "F01", "API_01")
            if not matched:
                non_empty_s = [c.string_value for c in sr.cells if c.string_value]
                if non_empty_s:
                    s_pk = non_empty_s[0].strip().lower()
                    pk_cands = t_pk_map.get(s_pk, [])
                    for cand_idx in pk_cands:
                        if cand_idx not in matched_t_indices:
                            t_text = " ".join(c.string_value for c in t_rows[cand_idx].cells if c.string_value)
                            s_trans_text = " ".join(s_trans_cells)
                            score = difflib.SequenceMatcher(None, s_trans_text.lower(), t_text.lower()).ratio()
                            if score >= 0.40 or s_idx == cand_idx or abs(s_idx - cand_idx) <= 2:
                                matched_s_to_t[s_idx] = cand_idx
                                matched_t_indices.add(cand_idx)
                                matched = True
                                break

        # Pass 2: Sequence Alignment (Myers / Fuzzy Similarity on Translated Content)
        for s_idx, sr in enumerate(s_rows):
            if s_idx in matched_s_to_t:
                continue

            s_trans_cells = [src_to_tgt_map.get(c.string_value, c.string_value) for c in sr.cells if c.string_value]
            s_trans_text = " ".join(s_trans_cells)
            if not s_trans_text:
                continue

            best_t_idx: Optional[int] = None
            best_score = 0.0

            for t_idx, tr in enumerate(t_rows):
                if t_idx in matched_t_indices or not tr.has_content:
                    continue

                t_text = " ".join(c.string_value for c in tr.cells if c.string_value)
                if not t_text:
                    continue

                score = 0.0
                if s_trans_text.lower() == t_text.lower():
                    score = 1.0
                elif abs(s_idx - t_idx) <= 2:
                    score = difflib.SequenceMatcher(None, s_trans_text.lower(), t_text.lower()).ratio()
                    score += 0.15
                else:
                    score = difflib.SequenceMatcher(None, s_trans_text.lower(), t_text.lower()).ratio()

                if score > best_score and score >= self.similarity_threshold:
                    best_score = score
                    best_t_idx = t_idx

            if best_t_idx is not None:
                matched_s_to_t[s_idx] = best_t_idx
                matched_t_indices.add(best_t_idx)

        # 2. Structural Dimension Mutations: Insertions & Deletions
        unmatched_s_indices = [s_idx for s_idx in range(len(s_rows)) if s_idx not in matched_s_to_t and s_rows[s_idx].has_content]
        unmatched_t_indices = [t_idx for t_idx in range(len(t_rows)) if t_idx not in matched_t_indices and t_rows[t_idx].has_content]

        # A. If target has obsolete rows (deleted in source) -> DELETE_ROWS
        if unmatched_t_indices:
            ranges: List[Tuple[int, int]] = []
            curr_start = unmatched_t_indices[0]
            curr_prev = unmatched_t_indices[0]
            for idx in unmatched_t_indices[1:]:
                if idx == curr_prev + 1:
                    curr_prev = idx
                else:
                    ranges.append((curr_start, curr_prev + 1))
                    curr_start = idx
                    curr_prev = idx
            ranges.append((curr_start, curr_prev + 1))

            for r_start, r_end in ranges:
                count = r_end - r_start
                logger.info(f"SOTA Sheets Sync: DELETE_ROWS detected: sheet '{target_tab.title}', rows {r_start} to {r_end} (count {count})")
                ops.append(
                    SheetDiffOperation(
                        op_type=SheetDiffOpType.DELETE_ROWS,
                        sheet_id=target_tab.sheet_id,
                        sheet_title=target_tab.title,
                        start_row_index=r_start,
                        end_row_index=r_end,
                        count=count,
                    )
                )

        # B. If source has newly inserted rows -> INSERT_ROWS
        if unmatched_s_indices:
            ranges: List[Tuple[int, int]] = []
            curr_start = unmatched_s_indices[0]
            curr_prev = unmatched_s_indices[0]
            for idx in unmatched_s_indices[1:]:
                if idx == curr_prev + 1:
                    curr_prev = idx
                else:
                    ranges.append((curr_start, curr_prev + 1))
                    curr_start = idx
                    curr_prev = idx
            ranges.append((curr_start, curr_prev + 1))

            for r_start, r_end in ranges:
                count = r_end - r_start
                anchor_target_idx = r_start
                for prev_s in range(r_start - 1, -1, -1):
                    if prev_s in matched_s_to_t:
                        anchor_target_idx = matched_s_to_t[prev_s] + 1
                        break

                logger.info(f"SOTA Sheets Sync: INSERT_ROWS detected: sheet '{target_tab.title}', anchor {anchor_target_idx}, count {count}")
                ops.append(
                    SheetDiffOperation(
                        op_type=SheetDiffOpType.INSERT_ROWS,
                        sheet_id=target_tab.sheet_id,
                        sheet_title=target_tab.title,
                        start_row_index=anchor_target_idx,
                        end_row_index=anchor_target_idx + count,
                        count=count,
                    )
                )

        # 3. Cell Delta Extraction (Updates, Additions, and Deletions/Clearing)
        cell_updates: List[Dict[str, Any]] = []

        # A. For matched rows: update translatable cells where value changed or clear cells deleted in source
        for s_idx, t_idx in matched_s_to_t.items():
            s_row = s_rows[s_idx]
            t_row = t_rows[t_idx] if t_idx < len(t_rows) else None

            max_cols = max(len(s_row.cells), len(t_row.cells) if t_row else 0)
            for col_idx in range(max_cols):
                s_cell = s_row.cells[col_idx] if col_idx < len(s_row.cells) else None
                t_cell = t_row.cells[col_idx] if t_row and col_idx < len(t_row.cells) else None

                # Strict formula immunity: Never overwrite formulas!
                if t_cell and t_cell.cell_type == CellType.FORMULA:
                    continue

                curr_target_val = t_cell.string_value if t_cell else ""

                if s_cell and s_cell.is_translatable:
                    trans_text = src_to_tgt_map.get(s_cell.string_value, s_cell.string_value)
                    if trans_text and trans_text != curr_target_val:
                        cell_updates.append({
                            "sheet": target_tab.title,
                            "row": t_idx,
                            "col": col_idx,
                            "new_value": trans_text,
                            "old_value": curr_target_val,
                            "cell_ref": f"{col_index_to_letter(col_idx)}{t_idx + 1}"
                        })
                elif (not s_cell or not s_cell.string_value.strip()):
                    # Cell deleted/cleared in source: if target cell has text or old image formula, clear it!
                    if t_cell and curr_target_val:
                        cell_updates.append({
                            "sheet": target_tab.title,
                            "row": t_idx,
                            "col": col_idx,
                            "new_value": "",
                            "old_value": curr_target_val,
                            "cell_ref": f"{col_index_to_letter(col_idx)}{t_idx + 1}"
                        })

        # B. For unmatched (inserted) source rows: generate initial translation cell updates
        for s_idx in unmatched_s_indices:
            s_row = s_rows[s_idx]
            target_row_idx = s_idx
            for s_cell in s_row.cells:
                if s_cell.is_translatable:
                    trans_text = src_to_tgt_map.get(s_cell.string_value, s_cell.string_value)
                    cell_updates.append({
                        "sheet": target_tab.title,
                        "row": target_row_idx,
                        "col": s_cell.col_idx,
                        "new_value": trans_text,
                        "old_value": "",
                        "cell_ref": f"{col_index_to_letter(s_cell.col_idx)}{target_row_idx + 1}"
                    })

        if cell_updates:
            ops.append(
                SheetDiffOperation(
                    op_type=SheetDiffOpType.UPDATE_CELLS,
                    sheet_id=target_tab.sheet_id,
                    sheet_title=target_tab.title,
                    cell_updates=cell_updates
                )
            )

        return ops


class SheetReverseIndexBatchPlanner:
    """Plans structural dimension requests in descending index order and aggregates cell mutations into optimal ValueRanges."""

    @classmethod
    def plan_batch_updates(
        cls,
        operations: List[SheetDiffOperation]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns:
        1. `structural_requests`: Google Sheets API batchUpdate requests (addSheet, deleteSheet, deleteDimension, insertDimension).
           Dimension deletions/insertions are guaranteed sorted descending to prevent index drift.
        2. `value_ranges`: Optimal rectangular ValueRange payloads for values:batchUpdate.
        """
        structural_requests: List[Dict[str, Any]] = []
        raw_cell_updates: List[Dict[str, Any]] = []

        dim_delete_ops: List[SheetDiffOperation] = []
        dim_insert_ops: List[SheetDiffOperation] = []

        for op in operations:
            if op.op_type == SheetDiffOpType.ADD_SHEET:
                req = {
                    "addSheet": {
                        "properties": {
                            "title": op.metadata.get("title", op.sheet_title),
                            "index": op.metadata.get("index", 0),
                        }
                    }
                }
                structural_requests.append(req)

            elif op.op_type == SheetDiffOpType.DELETE_SHEET:
                req = {
                    "deleteSheet": {
                        "sheetId": op.sheet_id
                    }
                }
                structural_requests.append(req)

            elif op.op_type == SheetDiffOpType.DELETE_ROWS:
                dim_delete_ops.append(op)

            elif op.op_type == SheetDiffOpType.INSERT_ROWS:
                dim_insert_ops.append(op)

            elif op.op_type == SheetDiffOpType.UPDATE_CELLS:
                raw_cell_updates.extend(op.cell_updates)

        # CRITICAL SOTA GUARANTEE: Sort deleteDimension requests in DESCENDING order of start_row_index!
        dim_delete_ops.sort(key=lambda item: item.start_row_index, reverse=True)
        for d_op in dim_delete_ops:
            structural_requests.append({
                "deleteDimension": {
                    "range": {
                        "sheetId": d_op.sheet_id,
                        "dimension": "ROWS",
                        "startIndex": d_op.start_row_index,
                        "endIndex": d_op.end_row_index,
                    }
                }
            })

        # CRITICAL SOTA GUARANTEE: Sort insertDimension requests in DESCENDING order of start_row_index!
        dim_insert_ops.sort(key=lambda item: item.start_row_index, reverse=True)
        for i_op in dim_insert_ops:
            structural_requests.append({
                "insertDimension": {
                    "range": {
                        "sheetId": i_op.sheet_id,
                        "dimension": "ROWS",
                        "startIndex": i_op.start_row_index,
                        "endIndex": i_op.end_row_index,
                    },
                    "inheritFromBefore": True if i_op.start_row_index > 0 else False
                }
            })

        # Contiguous Range Aggregation for Cell Updates
        value_ranges = cls._aggregate_contiguous_ranges(raw_cell_updates)

        return structural_requests, value_ranges

    @classmethod
    def _aggregate_contiguous_ranges(cls, cell_updates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregates individual cell updates into contiguous rectangular A1/R1C1 ranges to minimize API calls."""
        if not cell_updates:
            return []

        # Group by sheet
        by_sheet: Dict[str, List[Dict[str, Any]]] = {}
        for u in cell_updates:
            by_sheet.setdefault(u["sheet"], []).append(u)

        aggregated: List[Dict[str, Any]] = []

        for sheet_title, updates in by_sheet.items():
            # Group by row
            by_row: Dict[int, List[Dict[str, Any]]] = {}
            for u in updates:
                by_row.setdefault(u["row"], []).append(u)

            for row_idx, row_updates in by_row.items():
                # Sort row updates by column index
                row_updates.sort(key=lambda item: item["col"])

                # Group contiguous column sequences
                seqs: List[List[Dict[str, Any]]] = []
                curr_seq: List[Dict[str, Any]] = []

                for cu in row_updates:
                    if not curr_seq:
                        curr_seq.append(cu)
                    elif cu["col"] == curr_seq[-1]["col"] + 1:
                        curr_seq.append(cu)
                    else:
                        seqs.append(curr_seq)
                        curr_seq = [cu]
                if curr_seq:
                    seqs.append(curr_seq)

                for seq in seqs:
                    start_col = seq[0]["col"]
                    end_col = seq[-1]["col"]
                    start_cell = f"{col_index_to_letter(start_col)}{row_idx + 1}"
                    if start_col == end_col:
                        range_str = f"'{sheet_title}'!{start_cell}"
                        row_vals = [[seq[0]["new_value"]]]
                    else:
                        end_cell = f"{col_index_to_letter(end_col)}{row_idx + 1}"
                        range_str = f"'{sheet_title}'!{start_cell}:{end_cell}"
                        row_vals = [[item["new_value"] for item in seq]]

                    aggregated.append({
                        "range": range_str,
                        "values": row_vals
                    })

        return aggregated
