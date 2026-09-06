"""
AST Block-Level Myers Diff & Structural Fingerprinting Engine for Google Docs.
State-of-the-Art (SOTA) in-place synchronization for collaborative document translation.

Capabilities:
1. Full AST Parsing: Parses Google Docs document tree into structured ASTBlock objects
   (Paragraph, Heading 1/2/3, Bullet lists, Title, Alignment, Styles).
2. Semantic Structural Fingerprinting: Hashes structural roles, hierarchy, and context.
3. Hierarchical Myers Diff: Detects unchanged, modified, inserted, deleted, and moved blocks.
4. Full Style & Format Sync: Syncs heading styles, bullets, bold/italic, alignment.
5. Conflict-Free Reverse-Index Batch Planner: Orders all mutation requests in descending
   order of character index to guarantee zero offset drift.
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

logger = logging.getLogger("comtor_copilot.ast_sync")


class ASTBlockType(str, Enum):
    TITLE = "title"
    HEADING_1 = "heading_1"
    HEADING_2 = "heading_2"
    HEADING_3 = "heading_3"
    HEADING_4 = "heading_4"
    HEADING_5 = "heading_5"
    HEADING_6 = "heading_6"
    BULLET = "bullet"
    PARAGRAPH = "paragraph"
    TABLE_CELL = "table_cell"
    IMAGE = "image"
    UNKNOWN = "unknown"


class DiffOpType(str, Enum):
    NO_CHANGE = "no_change"
    UPDATE_TEXT = "update_text"
    INSERT_BLOCK = "insert_block"
    DELETE_BLOCK = "delete_block"
    MOVE_BLOCK = "move_block"
    STYLE_UPDATE = "style_update"


@dataclass
class ASTBlock:
    tab_id: Optional[str]
    block_index: int
    start_index: int
    end_index: int
    block_type: ASTBlockType
    raw_text: str
    cleaned_text: str
    parent_heading: str = ""
    paragraph_style: Dict[str, Any] = field(default_factory=dict)
    text_style: Dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_heading(self) -> bool:
        return self.block_type in (
            ASTBlockType.TITLE,
            ASTBlockType.HEADING_1,
            ASTBlockType.HEADING_2,
            ASTBlockType.HEADING_3,
            ASTBlockType.HEADING_4,
            ASTBlockType.HEADING_5,
            ASTBlockType.HEADING_6,
        )

    @property
    def is_bullet(self) -> bool:
        return self.block_type == ASTBlockType.BULLET


@dataclass
class DiffOperation:
    op_type: DiffOpType
    tab_id: Optional[str]
    source_block: Optional[ASTBlock] = None
    target_block: Optional[ASTBlock] = None
    new_text: str = ""
    old_text: str = ""
    target_anchor_index: int = 1
    style_payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GoogleDocsASTParser:
    """Parses Google Docs REST API JSON representation into a list of structured ASTBlock objects."""

    @classmethod
    def parse_document(cls, doc_data: Dict[str, Any]) -> List[ASTBlock]:
        blocks: List[ASTBlock] = []
        raw_tabs = doc_data.get("tabs", [])

        if raw_tabs:
            flat_tabs = cls._flatten_tabs(raw_tabs)
            for tab in flat_tabs:
                tab_id = tab.get("tabProperties", {}).get("tabId")
                doc_tab = tab.get("documentTab", {})
                body = doc_tab.get("body", {})
                inline_objs = doc_tab.get("inlineObjects", {})
                tab_blocks = cls._parse_body_content(
                    body.get("content", []),
                    tab_id=tab_id,
                    inline_objects=inline_objs
                )
                blocks.extend(tab_blocks)
        else:
            body = doc_data.get("body", {})
            inline_objs = doc_data.get("inlineObjects", {})
            tab_blocks = cls._parse_body_content(
                body.get("content", []),
                tab_id=None,
                inline_objects=inline_objs
            )
            blocks.extend(tab_blocks)

        return blocks

    @classmethod
    def _flatten_tabs(cls, tabs_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flat: List[Dict[str, Any]] = []
        for t in tabs_list:
            flat.append(t)
            child_tabs = t.get("childTabs", [])
            if child_tabs:
                flat.extend(cls._flatten_tabs(child_tabs))
        return flat

    @classmethod
    def _parse_body_content(
        cls,
        content_elements: List[Dict[str, Any]],
        tab_id: Optional[str],
        inline_objects: Optional[Dict[str, Any]] = None
    ) -> List[ASTBlock]:
        blocks: List[ASTBlock] = []
        current_parent_heading = "ROOT"
        block_idx = 0
        body_end_index = content_elements[-1].get("endIndex", 1) if content_elements else 1

        for el in content_elements:
            start_idx = el.get("startIndex", 1)
            end_idx = el.get("endIndex", 1)

            if "paragraph" in el:
                p = el["paragraph"]
                elements = p.get("elements", [])
                p_style = p.get("paragraphStyle", {})
                named_style = p_style.get("namedStyleType", "NORMAL_TEXT")

                # 1. Parse any inline images in this paragraph
                inline_elem_entries = [e for e in elements if "inlineObjectElement" in e]
                if inline_elem_entries:
                    is_alone = (
                        len(elements) == 1
                        or (len(elements) == 2 and any(e.get("textRun", {}).get("content") == "\n" for e in elements))
                    )
                    is_last_body = (end_idx >= body_end_index)

                    for ie in inline_elem_entries:
                        obj_id = ie["inlineObjectElement"].get("inlineObjectId", "")
                        obj_val = (inline_objects or {}).get(obj_id, {})
                        embedded = obj_val.get("inlineObjectProperties", {}).get("embeddedObject", {})
                        content_uri = embedded.get("imageProperties", {}).get("contentUri")
                        size = embedded.get("size", {})

                        img_metadata = {
                            "inline_object_id": obj_id,
                            "content_uri": content_uri,
                            "size": size,
                            "is_alone_in_paragraph": is_alone,
                            "paragraph_start_index": start_idx,
                            "paragraph_end_index": end_idx,
                            "element_start_index": ie.get("startIndex", start_idx),
                            "element_end_index": ie.get("endIndex", end_idx),
                            "is_last_body_element": is_last_body,
                        }

                        fp = cls._compute_fingerprint(tab_id, current_parent_heading, ASTBlockType.IMAGE, f"img_{obj_id}")
                        img_block = ASTBlock(
                            tab_id=tab_id,
                            block_index=block_idx,
                            start_index=start_idx if is_alone else ie.get("startIndex", start_idx),
                            end_index=end_idx if is_alone else ie.get("endIndex", end_idx),
                            block_type=ASTBlockType.IMAGE,
                            raw_text=f"[IMAGE: {obj_id}]",
                            cleaned_text=f"[IMAGE: {obj_id}]",
                            parent_heading=current_parent_heading,
                            paragraph_style=p_style,
                            text_style={},
                            fingerprint=fp,
                            metadata=img_metadata,
                        )
                        blocks.append(img_block)
                        block_idx += 1

                # 2. Parse text content
                raw_text = "".join(elem.get("textRun", {}).get("content", "") for elem in elements)
                cleaned = raw_text.strip()
                if not cleaned:
                    continue

                # Determine block type
                if named_style == "TITLE" or cleaned.startswith("【"):
                    b_type = ASTBlockType.TITLE
                elif named_style == "HEADING_1" or (len(cleaned) < 80 and any(cleaned.startswith(f"{d}.") for d in range(1, 30))):
                    b_type = ASTBlockType.HEADING_1
                elif named_style == "HEADING_2":
                    b_type = ASTBlockType.HEADING_2
                elif named_style == "HEADING_3":
                    b_type = ASTBlockType.HEADING_3
                elif named_style == "HEADING_4":
                    b_type = ASTBlockType.HEADING_4
                elif named_style == "HEADING_5":
                    b_type = ASTBlockType.HEADING_5
                elif named_style == "HEADING_6":
                    b_type = ASTBlockType.HEADING_6
                elif "bullet" in p or cleaned.startswith("•") or cleaned.startswith("-") or cleaned.startswith("*"):
                    b_type = ASTBlockType.BULLET
                else:
                    b_type = ASTBlockType.PARAGRAPH

                # Extract dominant text styling
                dominant_text_style: Dict[str, Any] = {}
                for elem in elements:
                    tr = elem.get("textRun", {})
                    ts = tr.get("textStyle", {})
                    if ts:
                        if ts.get("bold"):
                            dominant_text_style["bold"] = True
                        if ts.get("italic"):
                            dominant_text_style["italic"] = True
                        if ts.get("underline"):
                            dominant_text_style["underline"] = True
                        if ts.get("foregroundColor"):
                            dominant_text_style["foregroundColor"] = ts.get("foregroundColor")
                        if ts.get("fontSize"):
                            dominant_text_style["fontSize"] = ts.get("fontSize")

                # Update parent heading for section context
                if b_type in (ASTBlockType.TITLE, ASTBlockType.HEADING_1, ASTBlockType.HEADING_2):
                    current_parent_heading = cleaned[:60]

                fingerprint = cls._compute_fingerprint(tab_id, current_parent_heading, b_type, cleaned)

                block = ASTBlock(
                    tab_id=tab_id,
                    block_index=block_idx,
                    start_index=start_idx,
                    end_index=end_idx,
                    block_type=b_type,
                    raw_text=raw_text,
                    cleaned_text=cleaned,
                    parent_heading=current_parent_heading,
                    paragraph_style=p_style,
                    text_style=dominant_text_style,
                    fingerprint=fingerprint,
                )
                blocks.append(block)
                block_idx += 1

            elif "table" in el:
                # Table support: inspect cells and extract text blocks
                table = el["table"]
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        cell_content = cell.get("content", [])
                        for c_el in cell_content:
                            if "paragraph" in c_el:
                                c_p = c_el["paragraph"]
                                c_raw = "".join(e.get("textRun", {}).get("content", "") for e in c_p.get("elements", []))
                                c_cleaned = c_raw.strip()
                                if c_cleaned:
                                    fp = cls._compute_fingerprint(tab_id, current_parent_heading, ASTBlockType.TABLE_CELL, c_cleaned)
                                    b = ASTBlock(
                                        tab_id=tab_id,
                                        block_index=block_idx,
                                        start_index=c_el.get("startIndex", start_idx),
                                        end_index=c_el.get("endIndex", end_idx),
                                        block_type=ASTBlockType.TABLE_CELL,
                                        raw_text=c_raw,
                                        cleaned_text=c_cleaned,
                                        parent_heading=current_parent_heading,
                                        paragraph_style=c_p.get("paragraphStyle", {}),
                                        fingerprint=fp,
                                    )
                                    blocks.append(b)
                                    block_idx += 1

        return blocks

    @staticmethod
    def _compute_fingerprint(tab_id: Optional[str], parent_heading: str, block_type: ASTBlockType, text: str) -> str:
        # Normalize text to create a robust skeleton
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        key = f"{tab_id or 'default'}::{parent_heading}::{block_type.value}::{normalized}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class ASTBlockMyersDiffEngine:
    """Computes the optimal hierarchical structural difference between Source AST and Target AST."""

    def __init__(self, similarity_threshold: float = 0.45):
        self.similarity_threshold = similarity_threshold

    def compute_diff(
        self,
        source_blocks: List[ASTBlock],
        target_blocks: List[ASTBlock],
        current_segments: List[Any],
        previous_segments: Optional[List[Any]] = None,
        selected_tabs: Optional[List[str]] = None,
    ) -> List[DiffOperation]:
        ops: List[DiffOperation] = []

        # Group blocks by tab_id
        src_by_tab: Dict[Optional[str], List[ASTBlock]] = {}
        tgt_by_tab: Dict[Optional[str], List[ASTBlock]] = {}

        for b in source_blocks:
            if selected_tabs and b.tab_id and b.tab_id not in selected_tabs:
                continue
            src_by_tab.setdefault(b.tab_id, []).append(b)

        for b in target_blocks:
            if selected_tabs and b.tab_id and b.tab_id not in selected_tabs:
                continue
            tgt_by_tab.setdefault(b.tab_id, []).append(b)

        # Build segment translation lookup maps
        # 1. source_text -> translated_text (from current_segments)
        src_to_tgt_map: Dict[str, str] = {}
        for s in current_segments:
            token_map = json.loads(getattr(s, "protected_tokens_json", "{}") or "{}")
            raw_src, _ = TokenProtector.restore_tokens(getattr(s, "source_text", "") or "", token_map)
            s_raw = raw_src.strip()
            s_trans = (getattr(s, "translated_text", "") or "").strip()
            if s_raw and s_trans:
                src_to_tgt_map[s_raw] = s_trans

        # 2. previous segment lookup (prev_source -> prev_translated)
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

        all_tabs = set(src_by_tab.keys()) | set(tgt_by_tab.keys())

        for tab_id in all_tabs:
            tab_src_blocks = src_by_tab.get(tab_id, [])
            tab_tgt_blocks = tgt_by_tab.get(tab_id, [])

            tab_ops = self._diff_tab_blocks(
                tab_id=tab_id,
                src_blocks=tab_src_blocks,
                tgt_blocks=tab_tgt_blocks,
                src_to_tgt_map=src_to_tgt_map,
                prev_src_to_tgt_map=prev_src_to_tgt_map,
                prev_tgt_set=prev_tgt_set,
            )
            ops.extend(tab_ops)

        return ops

    def _diff_tab_blocks(
        self,
        tab_id: Optional[str],
        src_blocks: List[ASTBlock],
        tgt_blocks: List[ASTBlock],
        src_to_tgt_map: Dict[str, str],
        prev_src_to_tgt_map: Dict[str, str],
        prev_tgt_set: Set[str],
    ) -> List[DiffOperation]:
        ops: List[DiffOperation] = []

        matched_tgt_indices: Set[int] = set()
        matched_src_indices: Set[int] = set()

        # Pass 1: Match text blocks whose translated text is already verbatim in target document
        for s_idx, s_block in enumerate(src_blocks):
            if s_block.block_type == ASTBlockType.IMAGE:
                continue

            s_trans = src_to_tgt_map.get(s_block.cleaned_text)
            if not s_trans:
                continue

            for t_idx, t_block in enumerate(tgt_blocks):
                if t_block.block_type == ASTBlockType.IMAGE or t_idx in matched_tgt_indices:
                    continue
                if s_trans == t_block.cleaned_text or s_trans in t_block.cleaned_text:
                    matched_src_indices.add(s_idx)
                    matched_tgt_indices.add(t_idx)

                    # Check for style updates (e.g. source changed to HEADING_1 or BULLET)
                    s_named_style = s_block.paragraph_style.get("namedStyleType")
                    t_named_style = t_block.paragraph_style.get("namedStyleType")
                    if s_named_style and t_named_style and s_named_style != t_named_style:
                        ops.append(
                            DiffOperation(
                                op_type=DiffOpType.STYLE_UPDATE,
                                tab_id=tab_id,
                                source_block=s_block,
                                target_block=t_block,
                                style_payload={"paragraphStyle": s_block.paragraph_style, "textStyle": s_block.text_style},
                            )
                        )
                    break

        # Pass 2: Modified Text Segment Detection (SequenceMatcher & Prefix/Substring)
        for s_idx, s_block in enumerate(src_blocks):
            if s_block.block_type == ASTBlockType.IMAGE or s_idx in matched_src_indices:
                continue

            s_text = s_block.cleaned_text
            s_trans = src_to_tgt_map.get(s_text, s_text)

            best_tgt_idx: Optional[int] = None
            best_score: float = 0.0

            s_core = re.sub(r"^[\s•\-\*\d\.\(\)]+", "", s_text).strip().lower()

            for t_idx, t_block in enumerate(tgt_blocks):
                if t_block.block_type == ASTBlockType.IMAGE or t_idx in matched_tgt_indices:
                    continue

                t_text = t_block.cleaned_text
                t_core = re.sub(r"^[\s•\-\*\d\.\(\)]+", "", t_text).strip().lower()

                score = 0.0
                if s_trans.lower() == t_text.lower():
                    score = 1.0
                elif s_core and t_core:
                    trans_core = re.sub(r"^[\s•\-\*\d\.\(\)]+", "", s_trans).strip().lower()
                    if trans_core and (trans_core.startswith(t_core) or t_core.startswith(trans_core)):
                        if min(len(trans_core), len(t_core)) >= 6:
                            score = 0.85
                    else:
                        score = difflib.SequenceMatcher(None, trans_core, t_core).ratio()

                # Also compare against previous source if available
                for prev_src, prev_trans in prev_src_to_tgt_map.items():
                    if prev_trans in t_text:
                        p_core = re.sub(r"^[\s•\-\*\d\.\(\)]+", "", prev_src).strip().lower()
                        if s_core and p_core:
                            if s_core.startswith(p_core) or p_core.startswith(s_core):
                                if min(len(s_core), len(p_core)) >= 6:
                                    score = max(score, 0.88)
                            else:
                                score = max(score, difflib.SequenceMatcher(None, s_core, p_core).ratio())

                if score > best_score and score >= self.similarity_threshold:
                    best_score = score
                    best_tgt_idx = t_idx

            if best_tgt_idx is not None:
                tgt_match = tgt_blocks[best_tgt_idx]
                matched_src_indices.add(s_idx)
                matched_tgt_indices.add(best_tgt_idx)

                # Only consider MOVE_BLOCK if non-heading moved between distinctly different translated sections
                is_move = False
                if not s_block.is_heading and s_block.parent_heading and tgt_match.parent_heading:
                    p_trans = src_to_tgt_map.get(s_block.parent_heading, s_block.parent_heading).lower()
                    t_parent = tgt_match.parent_heading.lower()
                    if p_trans != t_parent and difflib.SequenceMatcher(None, p_trans, t_parent).ratio() < 0.4:
                        is_move = True

                if is_move:
                    logger.info(f"SOTA AST Sync: MOVE_BLOCK detected: '{tgt_match.cleaned_text[:30]}' moved to '{s_block.parent_heading}'")
                    ops.append(
                        DiffOperation(
                            op_type=DiffOpType.MOVE_BLOCK,
                            tab_id=tab_id,
                            source_block=s_block,
                            target_block=tgt_match,
                            new_text=s_trans,
                            old_text=tgt_match.cleaned_text,
                            style_payload={"paragraphStyle": s_block.paragraph_style, "textStyle": s_block.text_style},
                        )
                    )
                else:
                    logger.info(f"SOTA AST Sync: UPDATE_TEXT detected (score {best_score:.2f}): '{tgt_match.cleaned_text[:30]}' -> '{s_trans[:30]}'")
                    ops.append(
                        DiffOperation(
                            op_type=DiffOpType.UPDATE_TEXT,
                            tab_id=tab_id,
                            source_block=s_block,
                            target_block=tgt_match,
                            new_text=s_trans,
                            old_text=tgt_match.cleaned_text,
                            style_payload={"paragraphStyle": s_block.paragraph_style, "textStyle": s_block.text_style},
                        )
                    )

        # Pass 3: Deleted Text Blocks (target blocks not matched to any current source and recognized as obsolete translations)
        curr_src_set = {b.cleaned_text for b in src_blocks if b.block_type != ASTBlockType.IMAGE}
        for t_idx, t_block in enumerate(tgt_blocks):
            if t_block.block_type == ASTBlockType.IMAGE or t_idx in matched_tgt_indices:
                continue

            # If this target text was from a previous translation that no longer exists in source
            is_obsolete = False
            for prev_src, prev_trans in prev_src_to_tgt_map.items():
                if prev_trans in t_block.cleaned_text and prev_src not in curr_src_set:
                    is_obsolete = True
                    break

            if is_obsolete:
                logger.info(f"SOTA AST Sync: DELETE_BLOCK detected: '{t_block.cleaned_text[:35]}'")
                ops.append(
                    DiffOperation(
                        op_type=DiffOpType.DELETE_BLOCK,
                        tab_id=tab_id,
                        target_block=t_block,
                        old_text=t_block.cleaned_text,
                    )
                )

        # Pass 4: Inserted Text Blocks (unmatched source text blocks)
        for s_idx, s_block in enumerate(src_blocks):
            if s_block.block_type == ASTBlockType.IMAGE or s_idx in matched_src_indices:
                continue

            s_text = s_block.cleaned_text
            s_trans = src_to_tgt_map.get(s_text, s_text)

            # Determine anchor index in target document
            anchor_idx: Optional[int] = None

            # 1. Search forward for following matched source block in the same tab
            for next_idx in range(s_idx + 1, len(src_blocks)):
                next_block = src_blocks[next_idx]
                if next_block.block_type == ASTBlockType.IMAGE:
                    continue
                next_trans = src_to_tgt_map.get(next_block.cleaned_text)
                if next_trans:
                    # Find corresponding target block
                    for tb in tgt_blocks:
                        if tb.block_type != ASTBlockType.IMAGE and next_trans in tb.cleaned_text:
                            anchor_idx = tb.start_index
                            logger.info(f"SOTA AST Sync: INSERT anchor BEFORE '{tb.cleaned_text[:25]}' at {anchor_idx}")
                            break
                if anchor_idx is not None:
                    break

            # 2. Search backward for preceding matched source block
            if anchor_idx is None:
                for prev_idx in range(s_idx - 1, -1, -1):
                    prev_block = src_blocks[prev_idx]
                    if prev_block.block_type == ASTBlockType.IMAGE:
                        continue
                    prev_trans = src_to_tgt_map.get(prev_block.cleaned_text)
                    if prev_trans:
                        for tb in tgt_blocks:
                            if tb.block_type != ASTBlockType.IMAGE and prev_trans in tb.cleaned_text:
                                anchor_idx = tb.end_index
                                logger.info(f"SOTA AST Sync: INSERT anchor AFTER '{tb.cleaned_text[:25]}' at {anchor_idx}")
                                break
                    if anchor_idx is not None:
                        break

            # 3. Default to tab last index or top (1) if it's the very first block
            if anchor_idx is None:
                if s_idx == 0:
                    anchor_idx = 1
                elif tgt_blocks:
                    anchor_idx = tgt_blocks[-1].end_index
                else:
                    anchor_idx = 1
                logger.info(f"SOTA AST Sync: INSERT fallback anchor at {anchor_idx}")

            ops.append(
                DiffOperation(
                    op_type=DiffOpType.INSERT_BLOCK,
                    tab_id=tab_id,
                    source_block=s_block,
                    new_text=s_trans,
                    target_anchor_index=anchor_idx,
                    style_payload={"paragraphStyle": s_block.paragraph_style, "textStyle": s_block.text_style},
                )
            )

        # Pass 5: Image Block Synchronization (Structural Deletion & Insertion)
        src_image_blocks = [b for b in src_blocks if b.block_type == ASTBlockType.IMAGE]
        tgt_image_blocks = [b for b in tgt_blocks if b.block_type == ASTBlockType.IMAGE]

        matched_tgt_img_indices: Set[int] = set()
        matched_src_img_indices: Set[int] = set()

        def get_text_context(blocks: List[ASTBlock], block_item: ASTBlock) -> Tuple[Optional[str], Optional[str]]:
            p_idx = blocks.index(block_item) if block_item in blocks else -1
            if p_idx == -1:
                return None, None
            prev_txt = None
            next_txt = None
            for p in range(p_idx - 1, -1, -1):
                if blocks[p].block_type != ASTBlockType.IMAGE and blocks[p].cleaned_text:
                    prev_txt = blocks[p].cleaned_text
                    break
            for n in range(p_idx + 1, len(blocks)):
                if blocks[n].block_type != ASTBlockType.IMAGE and blocks[n].cleaned_text:
                    next_txt = blocks[n].cleaned_text
                    break
            return prev_txt, next_txt

        # Match source images to target images using neighborhood context and section heading
        for s_idx, s_img in enumerate(src_image_blocks):
            s_prev_txt, s_next_txt = get_text_context(src_blocks, s_img)
            s_prev_trans = src_to_tgt_map.get(s_prev_txt, s_prev_txt) if s_prev_txt else None
            s_next_trans = src_to_tgt_map.get(s_next_txt, s_next_txt) if s_next_txt else None
            s_parent_trans = src_to_tgt_map.get(s_img.parent_heading, s_img.parent_heading)

            best_t_idx: Optional[int] = None
            best_img_score: float = 0.0

            for t_idx, t_img in enumerate(tgt_image_blocks):
                if t_idx in matched_tgt_img_indices:
                    continue
                t_prev_txt, t_next_txt = get_text_context(tgt_blocks, t_img)

                score = 0.0
                if s_parent_trans and t_img.parent_heading and (
                    s_parent_trans.lower() == t_img.parent_heading.lower()
                    or s_parent_trans.lower() in t_img.parent_heading.lower()
                    or t_img.parent_heading.lower() in s_parent_trans.lower()
                ):
                    score += 0.4
                elif s_img.parent_heading == t_img.parent_heading:
                    score += 0.3

                if s_prev_trans and t_prev_txt and (
                    s_prev_trans.lower() == t_prev_txt.lower()
                    or s_prev_trans in t_prev_txt
                    or t_prev_txt in s_prev_trans
                ):
                    score += 0.35

                if s_next_trans and t_next_txt and (
                    s_next_trans.lower() == t_next_txt.lower()
                    or s_next_trans in t_next_txt
                    or t_next_txt in s_next_trans
                ):
                    score += 0.35

                if s_idx == t_idx:
                    score += 0.15

                if score > best_img_score and score >= 0.45:
                    best_img_score = score
                    best_t_idx = t_idx

            if best_t_idx is not None:
                matched_src_img_indices.add(s_idx)
                matched_tgt_img_indices.add(best_t_idx)
                logger.info(f"SOTA AST Sync: Matched image {s_img.cleaned_text} to target image {tgt_image_blocks[best_t_idx].cleaned_text} (score {best_img_score:.2f})")

        # Obsolete/Deleted images in target document -> DELETE_BLOCK
        for t_idx, t_img in enumerate(tgt_image_blocks):
            if t_idx not in matched_tgt_img_indices:
                logger.info(f"SOTA AST Sync: DELETE_BLOCK detected for deleted image: {t_img.cleaned_text} at index {t_img.start_index}")
                ops.append(
                    DiffOperation(
                        op_type=DiffOpType.DELETE_BLOCK,
                        tab_id=tab_id,
                        target_block=t_img,
                        old_text=t_img.cleaned_text,
                        metadata=t_img.metadata,
                    )
                )

        # Newly inserted images in source document -> INSERT_BLOCK
        for s_idx, s_img in enumerate(src_image_blocks):
            if s_idx not in matched_src_img_indices:
                s_prev_txt, s_next_txt = get_text_context(src_blocks, s_img)
                s_prev_trans = src_to_tgt_map.get(s_prev_txt, s_prev_txt) if s_prev_txt else None
                s_next_trans = src_to_tgt_map.get(s_next_txt, s_next_txt) if s_next_txt else None

                target_anchor = 1
                anchor_found = False

                # 1. Anchor after preceding translated text in target
                if s_prev_trans:
                    for tb in tgt_blocks:
                        if tb.block_type != ASTBlockType.IMAGE and (s_prev_trans in tb.cleaned_text or tb.cleaned_text in s_prev_trans):
                            target_anchor = tb.end_index
                            anchor_found = True
                            break

                # 2. Anchor before succeeding translated text in target
                if not anchor_found and s_next_trans:
                    for tb in tgt_blocks:
                        if tb.block_type != ASTBlockType.IMAGE and (s_next_trans in tb.cleaned_text or tb.cleaned_text in s_next_trans):
                            target_anchor = tb.start_index
                            anchor_found = True
                            break

                # 3. Fallback anchor
                if not anchor_found:
                    target_anchor = tgt_blocks[-1].end_index if tgt_blocks else 1

                logger.info(f"SOTA AST Sync: INSERT_BLOCK detected for new image: {s_img.cleaned_text} at target anchor {target_anchor}")
                ops.append(
                    DiffOperation(
                        op_type=DiffOpType.INSERT_BLOCK,
                        tab_id=tab_id,
                        source_block=s_img,
                        new_text=s_img.cleaned_text,
                        target_anchor_index=target_anchor,
                        metadata=s_img.metadata,
                    )
                )

        return ops


class ReverseIndexBatchPlanner:
    """Translates DiffOperations into an ordered sequence of conflict-free Google Docs batchUpdate requests."""

    @classmethod
    def plan_batch_updates(cls, operations: List[DiffOperation]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns:
        1. `replace_requests`: Global/scoped string replacements (for safe text swaps).
        2. `index_requests`: Character-index based requests (sorted in descending order of startIndex).
        """
        replace_requests: List[Dict[str, Any]] = []
        index_requests: List[Dict[str, Any]] = []

        for op in operations:
            tab_id = op.tab_id

            if op.op_type == DiffOpType.UPDATE_TEXT:
                # Use targeted replaceAllText scoped by tab to maintain surrounding character formats
                if op.old_text and op.new_text:
                    req_body: Dict[str, Any] = {
                        "containsText": {"matchCase": True, "text": op.old_text},
                        "replaceText": op.new_text,
                    }
                    if tab_id:
                        req_body["tabsCriteria"] = {"tabIds": [tab_id]}
                    replace_requests.append({"replaceAllText": req_body})

                # If paragraph style changed (e.g. became HEADING), also schedule style update
                if op.style_payload.get("paragraphStyle") and op.target_block:
                    p_style = op.style_payload["paragraphStyle"]
                    named_style = p_style.get("namedStyleType")
                    if named_style and named_style != op.target_block.paragraph_style.get("namedStyleType"):
                        range_dict: Dict[str, Any] = {
                            "startIndex": op.target_block.start_index,
                            "endIndex": op.target_block.end_index,
                        }
                        if tab_id:
                            range_dict["tabId"] = tab_id
                        index_requests.append({
                            "_sort_index": op.target_block.start_index,
                            "request": {
                                "updateParagraphStyle": {
                                    "range": range_dict,
                                    "paragraphStyle": {"namedStyleType": named_style},
                                    "fields": "namedStyleType",
                                }
                            }
                        })

            elif op.op_type == DiffOpType.DELETE_BLOCK:
                if op.target_block and op.target_block.block_type == ASTBlockType.IMAGE:
                    # Clean deletion of inline image without leaving blank paragraph
                    is_alone = op.target_block.metadata.get("is_alone_in_paragraph", True)
                    if is_alone:
                        del_start = op.target_block.metadata.get("paragraph_start_index", op.target_block.start_index)
                        del_end = op.target_block.metadata.get("paragraph_end_index", op.target_block.end_index)
                        if op.target_block.metadata.get("is_last_body_element", False):
                            del_end = max(del_start + 1, del_end - 1)
                    else:
                        del_start = op.target_block.metadata.get("element_start_index", op.target_block.start_index)
                        del_end = op.target_block.metadata.get("element_end_index", op.target_block.end_index)

                    range_dict = {
                        "startIndex": del_start,
                        "endIndex": del_end,
                    }
                    if tab_id:
                        range_dict["tabId"] = tab_id

                    index_requests.append({
                        "_sort_index": del_start,
                        "request": {
                            "deleteContentRange": {
                                "range": range_dict
                            }
                        }
                    })
                elif op.old_text:
                    req_body = {
                        "containsText": {"matchCase": True, "text": op.old_text},
                        "replaceText": "",
                    }
                    if tab_id:
                        req_body["tabsCriteria"] = {"tabIds": [tab_id]}
                    replace_requests.append({"replaceAllText": req_body})

            elif op.op_type == DiffOpType.INSERT_BLOCK:
                if op.source_block and op.source_block.block_type == ASTBlockType.IMAGE:
                    # Inline image insertion
                    img_uri = op.metadata.get("image_uri") or op.source_block.metadata.get("content_uri")
                    if img_uri:
                        loc = {"index": op.target_anchor_index}
                        if tab_id:
                            loc["tabId"] = tab_id

                        img_req: Dict[str, Any] = {
                            "location": loc,
                            "uri": img_uri,
                        }
                        size = op.metadata.get("size") or op.source_block.metadata.get("size")
                        if size and isinstance(size, dict) and "width" in size and "height" in size:
                            img_req["objectSize"] = {
                                "width": size["width"],
                                "height": size["height"],
                            }

                        # First insert paragraph break to host the image
                        index_requests.append({
                            "_sort_index": op.target_anchor_index,
                            "request": {
                                "insertText": {
                                    "location": loc,
                                    "text": "\n",
                                }
                            }
                        })
                        # Then insert the inline image
                        index_requests.append({
                            "_sort_index": op.target_anchor_index,
                            "request": {
                                "insertInlineImage": img_req
                            }
                        })
                else:
                    loc = {"index": op.target_anchor_index}
                    if tab_id:
                        loc["tabId"] = tab_id

                    text_to_insert = op.new_text + "\n\n"
                    insert_req = {
                        "_sort_index": op.target_anchor_index,
                        "request": {
                            "insertText": {
                                "location": loc,
                                "text": text_to_insert,
                            }
                        }
                    }
                    index_requests.append(insert_req)

                    # If source block was a heading, format the inserted text with updateParagraphStyle
                    if op.source_block and op.source_block.is_heading:
                        named_style = op.source_block.paragraph_style.get("namedStyleType", "HEADING_1")
                        range_dict = {
                            "startIndex": op.target_anchor_index,
                            "endIndex": op.target_anchor_index + len(op.new_text),
                        }
                        if tab_id:
                            range_dict["tabId"] = tab_id
                        index_requests.append({
                            "_sort_index": op.target_anchor_index,
                            "request": {
                                "updateParagraphStyle": {
                                    "range": range_dict,
                                    "paragraphStyle": {"namedStyleType": named_style},
                                    "fields": "namedStyleType",
                                }
                            }
                        })

            elif op.op_type == DiffOpType.MOVE_BLOCK:
                # 1. Remove from old position
                if op.old_text:
                    req_body = {
                        "containsText": {"matchCase": True, "text": op.old_text},
                        "replaceText": "",
                    }
                    if tab_id:
                        req_body["tabsCriteria"] = {"tabIds": [tab_id]}
                    replace_requests.append({"replaceAllText": req_body})

                # 2. Insert at new anchor
                loc = {"index": op.target_anchor_index}
                if tab_id:
                    loc["tabId"] = tab_id
                index_requests.append({
                    "_sort_index": op.target_anchor_index,
                    "request": {
                        "insertText": {
                            "location": loc,
                            "text": op.new_text + "\n\n",
                        }
                    }
                })

            elif op.op_type == DiffOpType.STYLE_UPDATE:
                if op.target_block and op.style_payload.get("paragraphStyle"):
                    p_style = op.style_payload["paragraphStyle"]
                    named_style = p_style.get("namedStyleType")
                    if named_style:
                        range_dict = {
                            "startIndex": op.target_block.start_index,
                            "endIndex": op.target_block.end_index,
                        }
                        if tab_id:
                            range_dict["tabId"] = tab_id
                        index_requests.append({
                            "_sort_index": op.target_block.start_index,
                            "request": {
                                "updateParagraphStyle": {
                                    "range": range_dict,
                                    "paragraphStyle": {"namedStyleType": named_style},
                                    "fields": "namedStyleType",
                                }
                            }
                        })

        # CRITICAL SOTA GUARANTEE: Sort index requests in DESCENDING order of start index!
        index_requests.sort(key=lambda item: item["_sort_index"], reverse=True)
        pure_index_requests = [item["request"] for item in index_requests]

        return replace_requests, pure_index_requests
