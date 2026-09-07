from typing import Dict, List, Any, Optional, Tuple
import httpx
import json
import re
import difflib
from app.core.logging import logger
from app.documents.segmenter import TokenProtector, ParsedSegment
from app.integrations.google.ast_sync import (
    ASTBlock,
    ASTBlockType,
    GoogleDocsASTParser,
    ASTBlockMyersDiffEngine,
    ReverseIndexBatchPlanner,
    DiffOpType,
)

DOCS_API_BASE = "https://docs.googleapis.com/v1/documents"

COMMON_TAB_TERMS_JA = [
    ("tổng quan & yêu cầu", "概要・要件"),
    ("tổng quan và yêu cầu", "概要・要件"),
    ("tổng quan", "概要"),
    ("kiến trúc & sơ đồ", "アーキテクチャ・図"),
    ("kiến trúc và sơ đồ", "アーキテクチャ・図"),
    ("kiến trúc hệ thống", "システムアーキテクチャ"),
    ("kiến trúc", "アーキテクチャ"),
    ("sơ đồ", "図・ダイアグラム"),
    ("thiết kế cơ sở dữ liệu", "データベース設計"),
    ("thiết kế csdl", "DB設計"),
    ("cơ sở dữ liệu", "データベース"),
    ("yêu cầu chức năng", "機能要件"),
    ("yêu cầu phi chức năng", "非機能要件"),
    ("yêu cầu", "要件"),
    ("giao diện người dùng", "ユーザーインターフェース"),
    ("giao diện", "画面・UI"),
    ("đặc tả yêu cầu", "要件定義"),
    ("đặc tả", "仕様"),
    ("báo cáo", "レポート"),
    ("danh sách", "一覧"),
    ("thông tin", "情報"),
    ("cấu hình", "設定"),
    ("hướng dẫn", "ガイド"),
    ("thẻ", "タブ"),
    ("trang tính", "シート"),
    ("trang", "ページ"),
]

def apply_smart_title_fallback(title: str, source_lang: str = "vi", target_lang: str = "ja") -> str:
    """Applies high-accuracy IT BrSE dictionary substitutions for tab/sheet titles if AI fails."""
    if not title or (target_lang or "").lower() != "ja":
        return title

    res = title
    for vi_phrase, ja_phrase in COMMON_TAB_TERMS_JA:
        pattern = re.compile(re.escape(vi_phrase), re.IGNORECASE)
        res = pattern.sub(ja_phrase, res)
    return res

class GoogleDocsService:
    """Manages Google Docs structured parsing, multi-tab support, table extraction, and non-destructive copy rendering via real Google Docs API."""

    @classmethod
    async def get_document_content(cls, access_token: str, document_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Fetches structured document JSON from Google Docs v1 API with multi-tab support."""
        if is_mock:
            return {
                "title": "Mock Google Doc",
                "revisionId": "mock-rev-1",
                "tabs": [
                    {
                        "tabProperties": {"tabId": "t.0", "title": "Tab 1"},
                        "documentTab": {
                            "body": {
                                "content": [
                                    {
                                        "paragraph": {
                                            "elements": [
                                                {"textRun": {"content": "Sample paragraph in mock tab."}}
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                ]
            }

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"includeTabsContent": "true"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(f"{DOCS_API_BASE}/{document_id}", headers=headers, params=params)
            if resp.status_code != 200:
                logger.error(f"Failed to get Google Doc {document_id}: {resp.text}")
                raise ValueError(f"Failed to fetch Google Doc: {resp.text}")
            return resp.json()

    @classmethod
    def _flatten_tabs(cls, tabs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recursively flattens nested tabs hierarchy from Google Docs API."""
        flat = []
        for t in tabs:
            flat.append(t)
            child_tabs = t.get("childTabs", [])
            if child_tabs:
                flat.extend(cls._flatten_tabs(child_tabs))
        return flat

    @classmethod
    def _parse_elements_list(
        cls,
        elements: List[Dict[str, Any]],
        tab_id: str,
        tab_title: str,
        context_prefix: str,
        segments: List[ParsedSegment],
        current_heading_ref: List[str],
        segment_idx_ref: List[int]
    ):
        """Recursively parses structural elements (paragraphs, tables, TOC) into translatable segments."""
        for item in elements:
            if "paragraph" in item:
                p = item["paragraph"]
                style = p.get("paragraphStyle", {}).get("namedStyleType", "")
                full_p_text = "".join(el.get("textRun", {}).get("content", "") for el in p.get("elements", [])).strip()
                if not full_p_text:
                    continue

                if "HEADING" in style:
                    current_heading_ref[0] = full_p_text

                protected_text, tags = TokenProtector.protect(full_p_text)
                hint_parts = []
                if tab_title:
                    hint_parts.append(f"Thẻ: {tab_title}")
                if context_prefix:
                    hint_parts.append(context_prefix)
                if current_heading_ref[0]:
                    hint_parts.append(current_heading_ref[0])
                hint = " - ".join(hint_parts) if hint_parts else "Đoạn văn"

                segments.append(ParsedSegment(
                    segment_index=segment_idx_ref[0],
                    source_text=protected_text,
                    location={
                        "type": "paragraph",
                        "tab_id": tab_id,
                        "tab_title": tab_title,
                        "p_index": segment_idx_ref[0]
                    },
                    protected_tokens=tags,
                    context_hint=hint,
                    formatting_meta={"style": style}
                ))
                segment_idx_ref[0] += 1

            elif "table" in item:
                table = item["table"]
                table_rows = table.get("tableRows", [])
                for r_idx, row in enumerate(table_rows):
                    table_cells = row.get("tableCells", [])
                    for c_idx, cell in enumerate(table_cells):
                        cell_content = cell.get("content", [])
                        cell_prefix = f"Bảng (hàng {r_idx + 1}, cột {c_idx + 1})"
                        cls._parse_elements_list(
                            cell_content,
                            tab_id,
                            tab_title,
                            cell_prefix,
                            segments,
                            current_heading_ref,
                            segment_idx_ref
                        )

            elif "tableOfContents" in item:
                toc_content = item["tableOfContents"].get("content", [])
                cls._parse_elements_list(
                    toc_content,
                    tab_id,
                    tab_title,
                    "Mục lục",
                    segments,
                    current_heading_ref,
                    segment_idx_ref
                )

    @classmethod
    def parse_segments(
        cls,
        doc_data: Dict[str, Any],
        selected_tabs: Optional[List[str]] = None
    ) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        """Parses Google Doc into standardized translatable segments, supporting multi-tabs and tables."""
        segments: List[ParsedSegment] = []
        raw_tabs = doc_data.get("tabs", [])
        flat_tabs = cls._flatten_tabs(raw_tabs) if raw_tabs else []

        segment_idx_ref = [0]
        processed_tabs = []

        if flat_tabs:
            for t in flat_tabs:
                props = t.get("tabProperties", {})
                tab_id = props.get("tabId", "")
                tab_title = props.get("title", "Tab")

                # Filter by selected tabs if provided (matching either ID or title)
                if selected_tabs and tab_id not in selected_tabs and tab_title not in selected_tabs:
                    continue

                processed_tabs.append({"id": tab_id, "title": tab_title})
                current_heading_ref = [tab_title]
                doc_tab = t.get("documentTab", {})
                body_content = doc_tab.get("body", {}).get("content", [])
                cls._parse_elements_list(
                    body_content,
                    tab_id,
                    tab_title,
                    "",
                    segments,
                    current_heading_ref,
                    segment_idx_ref
                )
        else:
            # Fallback for documents without tabs (single-tab or legacy body structure)
            doc_title = doc_data.get("title", "Document")
            processed_tabs.append({"id": "t.0", "title": doc_title})
            current_heading_ref = [doc_title]
            body_content = doc_data.get("body", {}).get("content", [])
            cls._parse_elements_list(
                body_content,
                "t.0",
                doc_title,
                "",
                segments,
                current_heading_ref,
                segment_idx_ref
            )

        all_tabs_info = [
            {
                "id": t.get("tabProperties", {}).get("tabId", ""),
                "title": t.get("tabProperties", {}).get("title", "Tab")
            }
            for t in flat_tabs
        ] if flat_tabs else [{"id": "t.0", "title": doc_data.get("title", "Document")}]

        metadata = {
            "title": doc_data.get("title", "Document"),
            "revision_id": doc_data.get("revisionId", "1"),
            "tabs": all_tabs_info,
            "processed_tabs": processed_tabs,
            "total_segments": len(segments)
        }
        return segments, metadata

    @classmethod
    async def get_metadata(cls, access_token: str, document_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Returns document title, tabs list, and segment count for frontend configuration."""
        data = await cls.get_document_content(access_token, document_id, is_mock=is_mock)
        segments, meta = cls.parse_segments(data)
        tabs_list = meta.get("tabs", [])
        return {
            "title": meta.get("title", "Google Doc"),
            "format": "gdoc",
            "tabs": tabs_list,
            "tab_names": [t["title"] for t in tabs_list if t.get("title")],
            "total_segments": len(segments)
        }

    @classmethod
    async def apply_translations_to_copy(
        cls,
        access_token: str,
        copy_document_id: str,
        translations: List[Dict[str, str]],
        selected_tabs: Optional[List[str]] = None,
        is_mock: bool = False
    ):
        """Applies batch updates to the translated copy via Google Docs API, supporting multi-tabs criteria."""
        if is_mock:
            return

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        requests = []
        for item in translations:
            src = item.get("source_text", "").strip()
            tgt = item.get("translated_text", "").strip()
            if src and tgt and src != tgt:
                req_body: Dict[str, Any] = {
                    "containsText": {"matchCase": True, "text": src},
                    "replaceText": tgt
                }
                if selected_tabs and len(selected_tabs) > 0:
                    req_body["tabsCriteria"] = {"tabIds": selected_tabs}
                requests.append({"replaceAllText": req_body})

        if requests:
            for i in range(0, len(requests), 50):
                chunk = requests[i:i + 50]
                async with httpx.AsyncClient(timeout=30.0) as http:
                    resp = await http.post(
                        f"{DOCS_API_BASE}/{copy_document_id}:batchUpdate",
                        headers=headers,
                        json={"requests": chunk}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"Failed to batch update Google Doc {copy_document_id}: {resp.text}")

    @classmethod
    async def apply_smart_delta_sync_to_existing_doc(
        cls,
        access_token: str,
        target_document_id: str,
        segments: List[Any],
        previous_segments: Optional[List[Any]] = None,
        source_document_id: Optional[str] = None,
        selected_tabs: Optional[List[str]] = None,
        parent_folder_id: Optional[str] = None,
        source_lang: str = "vi",
        target_lang: str = "ja",
        ocr_engine: str = "paddleocr",
        translate_images: bool = True,
        provider: Any = None,
        is_mock: bool = False
    ):
        """SOTA AST Block-Level Myers Diff & Structural Fingerprinting Sync for Google Docs in-place updates:
        1. Parses Google Docs AST into rich ASTBlocks (Paragraph, Heading 1/2/3, Bullet, Alignment, Styles, Images).
        2. Computes hierarchical Myers diff across sections, detecting UPDATE_TEXT, INSERT_BLOCK, DELETE_BLOCK (text and images), MOVE_BLOCK, and STYLE_UPDATE.
        3. Prepares any inserted images (with OCR translation if applicable and Drive temp upload).
        4. ReverseIndexBatchPlanner generates conflict-free, descending index sorted requests to eliminate offset drift.
        """
        if is_mock:
            return

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # 1. Fetch target doc AST
        target_doc = await cls.get_document_content(access_token, target_document_id, is_mock=is_mock)

        # 2. Fetch or construct source AST blocks
        source_doc = None
        source_blocks: List[ASTBlock] = []
        if source_document_id:
            try:
                source_doc = await cls.get_document_content(access_token, source_document_id, is_mock=is_mock)
            except Exception as src_err:
                logger.warning(f"Could not parse source document AST ({source_document_id}): {src_err}")

        # 3. Two-Phase Tab Synchronization (Phase 1: Tab Reconciliation)
        src_tabs = (source_doc or {}).get("tabs", [])
        tgt_tabs = target_doc.get("tabs", [])
        tab_map: Dict[str, str] = {}
        if src_tabs and tgt_tabs:
            tab_map = await cls.sync_document_tabs(
                access_token=access_token,
                target_document_id=target_document_id,
                source_tabs=src_tabs,
                target_tabs=tgt_tabs,
                source_lang=source_lang,
                target_lang=target_lang,
                provider=provider,
                is_mock=is_mock
            )
            flat_src_tabs = cls._flatten_tabs(src_tabs)
            flat_tgt_tabs = cls._flatten_tabs(tgt_tabs)
            if any(s.get("tabProperties", {}).get("tabId") not in [t.get("tabProperties", {}).get("tabId") for t in flat_tgt_tabs] for s in flat_src_tabs):
                target_doc = await cls.get_document_content(access_token, target_document_id, is_mock=is_mock)

        target_blocks = GoogleDocsASTParser.parse_document(target_doc)
        if source_doc:
            source_blocks = GoogleDocsASTParser.parse_document(source_doc)
            if tab_map:
                for b in source_blocks:
                    if b.tab_id and b.tab_id in tab_map:
                        b.tab_id = tab_map[b.tab_id]

        if not source_blocks and segments:
            # Build ASTBlocks from segments
            cur_heading = "ROOT"
            for i, seg in enumerate(segments):
                loc = json.loads(getattr(seg, "location_json", "{}") or "{}")
                tab_id = loc.get("tab_id")
                if tab_map and tab_id and tab_id in tab_map:
                    tab_id = tab_map[tab_id]
                token_map = json.loads(getattr(seg, "protected_tokens_json", "{}") or "{}")
                raw_src, _ = TokenProtector.restore_tokens(getattr(seg, "source_text", "") or "", token_map)
                cleaned = raw_src.strip()
                if not cleaned:
                    continue

                b_type = ASTBlockType.PARAGRAPH
                p_style = {"namedStyleType": "NORMAL_TEXT"}
                if cleaned.startswith("【") or (len(cleaned) < 80 and any(cleaned.startswith(f"{d}.") for d in range(1, 20))):
                    b_type = ASTBlockType.HEADING_1
                    p_style = {"namedStyleType": "HEADING_1"}
                    cur_heading = cleaned[:60]
                elif cleaned.startswith("•") or cleaned.startswith("-") or cleaned.startswith("*"):
                    b_type = ASTBlockType.BULLET

                fp = GoogleDocsASTParser._compute_fingerprint(tab_id, cur_heading, b_type, cleaned)
                source_blocks.append(ASTBlock(
                    tab_id=tab_id,
                    block_index=i,
                    start_index=1,
                    end_index=1,
                    block_type=b_type,
                    raw_text=raw_src,
                    cleaned_text=cleaned,
                    parent_heading=cur_heading,
                    paragraph_style=p_style,
                    fingerprint=fp
                ))

        # 3. Compute SOTA Myers Diff
        diff_engine = ASTBlockMyersDiffEngine(similarity_threshold=0.45)
        diff_ops = diff_engine.compute_diff(
            source_blocks=source_blocks,
            target_blocks=target_blocks,
            current_segments=segments,
            previous_segments=previous_segments,
            selected_tabs=selected_tabs
        )

        # 4. Prepare any newly inserted images (download, OCR translate if enabled, upload to Drive for public URL)
        temp_uploaded_drive_files: List[str] = []
        for op in diff_ops:
            if op.op_type == DiffOpType.INSERT_BLOCK and op.source_block and op.source_block.block_type == ASTBlockType.IMAGE:
                content_uri = op.source_block.metadata.get("content_uri")
                if not content_uri:
                    continue
                try:
                    async with httpx.AsyncClient(timeout=60.0) as http:
                        img_res = await http.get(content_uri)
                        if img_res.status_code == 200 and len(img_res.content) > 100:
                            img_bytes = img_res.content
                            if translate_images:
                                try:
                                    from app.documents.ocr.image_translator import image_translator
                                    trans_bytes = await image_translator.process_image(
                                        image_bytes=img_bytes,
                                        src_lang=source_lang,
                                        tgt_lang=target_lang,
                                        ocr_engine=ocr_engine,
                                        provider=provider
                                    )
                                    if trans_bytes and trans_bytes != img_bytes:
                                        img_bytes = trans_bytes
                                except Exception as ocr_err:
                                    logger.warning(f"Could not translate text in inserted image: {ocr_err}")

                            from app.integrations.google.drive import GoogleDriveService
                            import uuid
                            temp_filename = f"temp_sync_insert_{uuid.uuid4().hex[:8]}.png"
                            upload_res = await GoogleDriveService.upload_file(
                                access_token=access_token,
                                filename=temp_filename,
                                content_bytes=img_bytes,
                                mime_type="image/png",
                                parent_folder_id=parent_folder_id
                            )
                            temp_file_id = upload_res.get("id")
                            if temp_file_id:
                                temp_uploaded_drive_files.append(temp_file_id)
                                perm_res = await http.post(
                                    f"https://www.googleapis.com/drive/v3/files/{temp_file_id}/permissions?supportsAllDrives=true",
                                    headers={"Authorization": f"Bearer {access_token}"},
                                    json={"role": "reader", "type": "anyone"}
                                )
                                if perm_res.status_code not in (200, 201):
                                    logger.warning(f"Failed to set public permission on temp image {temp_file_id}: {perm_res.text}")
                                public_img_url = f"https://lh3.googleusercontent.com/d/{temp_file_id}"
                                op.metadata["image_uri"] = public_img_url
                                op.metadata["size"] = op.source_block.metadata.get("size")
                except Exception as img_err:
                    logger.warning(f"Failed to process inserted image for AST sync: {img_err}")

        try:
            replace_requests, index_requests = ReverseIndexBatchPlanner.plan_batch_updates(diff_ops)

            # 5. Also ensure any untranslated raw source segments found in target doc are replaced
            target_full_text = " ".join(tb.cleaned_text for tb in target_blocks)
            for seg in segments:
                token_map = json.loads(getattr(seg, "protected_tokens_json", "{}") or "{}")
                raw_src, _ = TokenProtector.restore_tokens(getattr(seg, "source_text", "") or "", token_map)
                src = raw_src.strip()
                tgt = (getattr(seg, "translated_text", "") or "").strip()
                if src and tgt and src != tgt and src in target_full_text:
                    req_body = {
                        "containsText": {"matchCase": True, "text": src},
                        "replaceText": tgt
                    }
                    if selected_tabs and len(selected_tabs) > 0:
                        req_body["tabsCriteria"] = {"tabIds": selected_tabs}
                    replace_requests.append({"replaceAllText": req_body})

            # 6. Execute batch replaceAllText requests
            if replace_requests:
                for i in range(0, len(replace_requests), 50):
                    chunk = replace_requests[i:i + 50]
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        resp = await http.post(
                            f"{DOCS_API_BASE}/{target_document_id}:batchUpdate",
                            headers=headers,
                            json={"requests": chunk}
                        )
                        if resp.status_code != 200:
                            logger.warning(f"Failed to batch replace in Google Doc {target_document_id}: {resp.text}")

            # 7. Execute index-based requests (sorted in descending index order)
            if index_requests:
                for i in range(0, len(index_requests), 20):
                    chunk = index_requests[i:i + 20]
                    async with httpx.AsyncClient(timeout=30.0) as http:
                        resp = await http.post(
                            f"{DOCS_API_BASE}/{target_document_id}:batchUpdate",
                            headers=headers,
                            json={"requests": chunk}
                        )
                        if resp.status_code != 200:
                            logger.warning(f"Failed to apply index-based AST mutations in Google Doc {target_document_id}: {resp.text}")
                        else:
                            logger.info(f"Successfully applied {len(chunk)} AST mutation requests into Google Doc {target_document_id}.")
        finally:
            if temp_uploaded_drive_files:
                from app.integrations.google.drive import GoogleDriveService
                for fid in temp_uploaded_drive_files:
                    try:
                        await GoogleDriveService.delete_file(access_token, fid)
                    except Exception as del_err:
                        logger.debug(f"Could not delete temp image file {fid}: {del_err}")


    @classmethod
    async def sync_document_tabs(
        cls,
        access_token: str,
        target_document_id: str,
        source_tabs: List[Dict[str, Any]],
        target_tabs: List[Dict[str, Any]],
        source_lang: str = "vi",
        target_lang: str = "ja",
        provider: Any = None,
        model: Optional[str] = None,
        is_mock: bool = False
    ) -> Dict[str, str]:
        """Two-Phase Tab Structural Reconciliation for Google Docs:
        1. Compares Source Tabs against Target Tabs using Multi-Stage Alignment (tabId -> title -> index).
        2. Detects newly added source tabs -> translates title -> calls addDocumentTab -> obtains new target_tab_id.
        3. Detects deleted target tabs -> calls deleteTab (preserving at least one tab).
        Returns:
            src_to_tgt_tab_map: Dict[str, str] mapping each source tabId to its corresponding target tabId.
        """
        src_to_tgt_tab_map: Dict[str, str] = {}
        if is_mock or not source_tabs or not target_tabs:
            for s in (source_tabs or []):
                sid = s.get("tabProperties", {}).get("tabId")
                if sid:
                    src_to_tgt_tab_map[sid] = sid
            return src_to_tgt_tab_map

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        flat_src = cls._flatten_tabs(source_tabs)
        flat_tgt = cls._flatten_tabs(target_tabs)

        tgt_by_id = {t.get("tabProperties", {}).get("tabId"): t for t in flat_tgt if t.get("tabProperties", {}).get("tabId")}
        tgt_by_title = {t.get("tabProperties", {}).get("title"): t for t in flat_tgt if t.get("tabProperties", {}).get("title")}
        tgt_by_index = {t.get("tabProperties", {}).get("index"): t for t in flat_tgt if t.get("tabProperties", {}).get("index") is not None}

        matched_src_ids: Set[str] = set()
        matched_tgt_ids: Set[str] = set()

        # Pass 1: Match by exact tabId (Primary Key - preserved across Drive copies)
        for s in flat_src:
            s_props = s.get("tabProperties", {})
            s_id = s_props.get("tabId")
            if s_id and s_id in tgt_by_id:
                t = tgt_by_id[s_id]
                t_id = t.get("tabProperties", {}).get("tabId")
                src_to_tgt_tab_map[s_id] = t_id
                matched_src_ids.add(s_id)
                matched_tgt_ids.add(t_id)

        # Pass 2: Match by exact title
        for s in flat_src:
            s_props = s.get("tabProperties", {})
            s_id = s_props.get("tabId")
            s_title = s_props.get("title")
            if s_id and s_id not in matched_src_ids and s_title in tgt_by_title:
                t = tgt_by_title[s_title]
                t_id = t.get("tabProperties", {}).get("tabId")
                if t_id not in matched_tgt_ids:
                    src_to_tgt_tab_map[s_id] = t_id
                    matched_src_ids.add(s_id)
                    matched_tgt_ids.add(t_id)

        # Pass 3: Match by positional index ONLY if no tabId matches were found across the document
        if not matched_src_ids:
            for s in flat_src:
                s_props = s.get("tabProperties", {})
                s_id = s_props.get("tabId")
                s_idx = s_props.get("index")
                if s_id and s_id not in matched_src_ids and s_idx in tgt_by_index:
                    t = tgt_by_index[s_idx]
                    t_id = t.get("tabProperties", {}).get("tabId")
                    if t_id not in matched_tgt_ids:
                        src_to_tgt_tab_map[s_id] = t_id
                        matched_src_ids.add(s_id)
                        matched_tgt_ids.add(t_id)

        # 1. Identify newly added source tabs
        added_source_tabs = [s for s in flat_src if s.get("tabProperties", {}).get("tabId") not in matched_src_ids]

        # 2. Identify obsolete target tabs to delete
        deleted_target_tabs = [t for t in flat_tgt if t.get("tabProperties", {}).get("tabId") not in matched_tgt_ids]

        # A. Execute addDocumentTab for new tabs
        if added_source_tabs:
            add_requests: List[Dict[str, Any]] = []
            add_src_ids: List[str] = []

            for s in added_source_tabs:
                s_props = s.get("tabProperties", {})
                s_id = s_props.get("tabId")
                orig_title = s_props.get("title", "New Tab")
                trans_title = apply_smart_title_fallback(orig_title, source_lang, target_lang)

                tab_props: Dict[str, Any] = {
                    "title": trans_title,
                    "index": s_props.get("index", len(flat_tgt) + len(add_requests))
                }
                if s_props.get("iconEmoji"):
                    tab_props["iconEmoji"] = s_props.get("iconEmoji")
                if s_props.get("parentTabId") and s_props.get("parentTabId") in src_to_tgt_tab_map:
                    tab_props["parentTabId"] = src_to_tgt_tab_map[s_props["parentTabId"]]

                add_requests.append({
                    "addDocumentTab": {
                        "tabProperties": tab_props
                    }
                })
                add_src_ids.append(s_id)

            logger.info(f"Two-Phase Tab Sync: Executing {len(add_requests)} addDocumentTab requests on Google Doc {target_document_id}")
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{DOCS_API_BASE}/{target_document_id}:batchUpdate",
                    headers=headers,
                    json={"requests": add_requests}
                )
                if resp.status_code == 200:
                    resp_json = resp.json()
                    import inspect
                    if inspect.iscoroutine(resp_json):
                        resp_json = await resp_json
                    replies = resp_json.get("replies", [])
                    for idx, reply in enumerate(replies):
                        add_reply = reply.get("addDocumentTab", {})
                        new_tab_props = add_reply.get("tabProperties", {})
                        new_tab_id = new_tab_props.get("tabId")
                        if new_tab_id and idx < len(add_src_ids):
                            src_id = add_src_ids[idx]
                            src_to_tgt_tab_map[src_id] = new_tab_id
                            logger.info(f"Two-Phase Tab Sync: Mapped source tab '{src_id}' -> newly created target tab '{new_tab_id}'")
                else:
                    logger.warning(f"Failed to add document tabs to Google Doc {target_document_id}: {resp.text}")

        # B. Execute deleteTab for obsolete target tabs (guaranteeing at least one tab remains)
        if deleted_target_tabs and (len(flat_tgt) - len(deleted_target_tabs) >= 1):
            del_requests: List[Dict[str, Any]] = []
            for t in deleted_target_tabs:
                t_id = t.get("tabProperties", {}).get("tabId")
                if t_id:
                    del_requests.append({
                        "deleteTab": {
                            "tabId": t_id
                        }
                    })
            if del_requests:
                logger.info(f"Two-Phase Tab Sync: Executing {len(del_requests)} deleteTab requests on Google Doc {target_document_id}")
                async with httpx.AsyncClient(timeout=30.0) as http:
                    del_resp = await http.post(
                        f"{DOCS_API_BASE}/{target_document_id}:batchUpdate",
                        headers=headers,
                        json={"requests": del_requests}
                    )
                    if del_resp.status_code != 200:
                        logger.warning(f"Failed to delete obsolete tabs on Google Doc {target_document_id}: {del_resp.text}")

        return src_to_tgt_tab_map

    @classmethod
    async def update_tab_titles(
        cls,
        access_token: str,
        copy_document_id: str,
        tab_title_updates: List[Dict[str, str]],
        is_mock: bool = False
    ):
        """Updates tab titles on the Google Docs tab bar using updateDocumentTabProperties."""
        if is_mock or not tab_title_updates:
            return

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        requests = []
        for item in tab_title_updates:
            tid = item.get("tab_id")
            title = item.get("title")
            if tid and title:
                requests.append({
                    "updateDocumentTabProperties": {
                        "tabProperties": {
                            "tabId": tid,
                            "title": title
                        },
                        "fields": "title"
                    }
                })

        if requests:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    f"{DOCS_API_BASE}/{copy_document_id}:batchUpdate",
                    headers=headers,
                    json={"requests": requests}
                )
                if resp.status_code != 200:
                    logger.warning(f"Failed to update tab titles on Google Doc {copy_document_id}: {resp.text}")
                else:
                    logger.info(f"Successfully updated {len(requests)} tab titles on Google Doc {copy_document_id}.")

    @classmethod
    async def translate_and_update_tab_titles(
        cls,
        access_token: str,
        copy_document_id: str,
        source_document_id: Optional[str] = None,
        source_lang: str = "vi",
        target_lang: str = "ja",
        provider: Any = None,
        model: Optional[str] = None,
        is_mock: bool = False
    ):
        """Translates document tab titles and updates them on the Google Docs tab bar."""
        if is_mock:
            return

        import json
        from app.engine.pipeline import clean_json_response

        doc_data = await cls.get_document_content(access_token, copy_document_id, is_mock=is_mock)
        raw_tabs = doc_data.get("tabs", [])
        flat_tabs = cls._flatten_tabs(raw_tabs) if raw_tabs else []
        if not flat_tabs:
            return

        source_title_map = {}
        if source_document_id:
            try:
                src_data = await cls.get_document_content(access_token, source_document_id, is_mock=is_mock)
                src_flat = cls._flatten_tabs(src_data.get("tabs", []))
                for idx, st in enumerate(src_flat):
                    st_props = st.get("tabProperties", {})
                    s_tid = st_props.get("tabId")
                    s_title = st_props.get("title", "").strip()
                    if s_tid:
                        source_title_map[s_tid] = s_title
                    source_title_map[f"idx_{idx}"] = s_title
            except Exception as src_err:
                logger.warning(f"Could not fetch source doc {source_document_id} for tab titles: {src_err}")

        titles_to_translate = []
        for idx, t in enumerate(flat_tabs):
            props = t.get("tabProperties", {})
            tid = props.get("tabId")
            orig_title = source_title_map.get(tid) or source_title_map.get(f"idx_{idx}") or props.get("title", "").strip()
            if tid and orig_title:
                titles_to_translate.append({"tab_id": tid, "title": orig_title})

        if not titles_to_translate:
            return

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
        prompt = f"""Translate the following tab titles from {source_lang} to {target_lang}. Keep them concise as UI tab titles (e.g., 'Thẻ 1 - Tổng quan' -> 'タブ 1 - 概要').
JSON input:
{json.dumps(items_payload, ensure_ascii=False)}

Return JSON matching:
{{"translations": [{{"id": 0, "translated": "..."}}]}}"""

        for current_prov, current_mod in providers_to_try:
            try:
                resp_data = await current_prov.generate(
                    prompt=prompt,
                    system_instruction=f"You are a professional translator from {source_lang} to {target_lang}. Translate concise UI/tab titles accurately.",
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
                    translated_title = trans_map.get(i) or trans_map.get(str(i))
                    if translated_title and translated_title.strip():
                        updates.append({
                            "tab_id": item["tab_id"],
                            "title": translated_title.strip()
                        })
                if updates:
                    break
            except Exception as e:
                logger.warning(f"Failed to translate tab titles with provider {getattr(current_prov, 'name', current_prov)}: {e}")

        # Smart fallback if updates is empty
        if not updates:
            for item in titles_to_translate:
                fallback_title = apply_smart_title_fallback(item["title"], source_lang, target_lang)
                updates.append({"tab_id": item["tab_id"], "title": fallback_title})

        await cls.update_tab_titles(access_token, copy_document_id, updates, is_mock=is_mock)

    @classmethod
    async def translate_embedded_images_in_copy(
        cls,
        access_token: str,
        copy_document_id: str,
        parent_folder_id: Optional[str] = None,
        source_lang: str = "vi",
        target_lang: str = "ja",
        ocr_engine: str = "paddleocr",
        provider: Any = None,
        is_mock: bool = False
    ):
        """Finds all inline images across all tabs of a Google Doc, translates them via ImageTranslator, and replaces them via replaceImage."""
        if is_mock:
            return

        from app.documents.ocr.image_translator import image_translator
        from app.integrations.google.drive import GoogleDriveService

        doc_data = await cls.get_document_content(access_token, copy_document_id, is_mock=is_mock)
        raw_tabs = doc_data.get("tabs", [])
        flat_tabs = cls._flatten_tabs(raw_tabs) if raw_tabs else []

        images_to_process = []
        if flat_tabs:
            for t in flat_tabs:
                tid = t.get("tabProperties", {}).get("tabId")
                inline_objs = t.get("documentTab", {}).get("inlineObjects", {})
                for obj_id, obj_val in inline_objs.items():
                    embedded = obj_val.get("inlineObjectProperties", {}).get("embeddedObject", {})
                    content_uri = embedded.get("imageProperties", {}).get("contentUri")
                    if content_uri:
                        images_to_process.append((obj_id, content_uri, tid))
        else:
            inline_objs = doc_data.get("inlineObjects", {})
            for obj_id, obj_val in inline_objs.items():
                embedded = obj_val.get("inlineObjectProperties", {}).get("embeddedObject", {})
                content_uri = embedded.get("imageProperties", {}).get("contentUri")
                if content_uri:
                    images_to_process.append((obj_id, content_uri, None))

        if not images_to_process:
            logger.info(f"No embedded images found in Google Doc {copy_document_id}.")
            return

        logger.info(f"Found {len(images_to_process)} embedded images to translate in Google Doc {copy_document_id}.")

        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=60.0) as http:
            for obj_id, content_uri, tab_id in images_to_process:
                try:
                    img_res = await http.get(content_uri)
                    if img_res.status_code != 200:
                        logger.warning(f"Could not download image {obj_id}: HTTP {img_res.status_code}")
                        continue
                    img_bytes = img_res.content
                    if len(img_bytes) < 100:
                        continue

                    translated_bytes = await image_translator.process_image(
                        image_bytes=img_bytes,
                        src_lang=source_lang,
                        tgt_lang=target_lang,
                        ocr_engine=ocr_engine,
                        provider=provider
                    )

                    if not translated_bytes or translated_bytes == img_bytes:
                        logger.info(f"Image {obj_id} was unchanged or no text detected.")
                        continue

                    upload_res = await GoogleDriveService.upload_file(
                        access_token=access_token,
                        filename=f"temp_translated_{obj_id}.png",
                        content_bytes=translated_bytes,
                        mime_type="image/png",
                        parent_folder_id=parent_folder_id
                    )
                    temp_file_id = upload_res.get("id")
                    if not temp_file_id:
                        continue

                    try:
                        perm_res = await http.post(
                            f"https://www.googleapis.com/drive/v3/files/{temp_file_id}/permissions?supportsAllDrives=true",
                            headers=headers,
                            json={"role": "reader", "type": "anyone"}
                        )
                        if perm_res.status_code not in (200, 201):
                            logger.warning(f"Failed to set public permission on temp image {temp_file_id}: {perm_res.text}")

                        img_url = f"https://lh3.googleusercontent.com/d/{temp_file_id}"
                        replace_body: Dict[str, Any] = {
                            "imageObjectId": obj_id,
                            "uri": img_url,
                            "imageReplaceMethod": "CENTER_CROP"
                        }
                        if tab_id:
                            replace_body["tabId"] = tab_id
                        rep_req = {"replaceImage": replace_body}
                        rep_res = await http.post(
                            f"{DOCS_API_BASE}/{copy_document_id}:batchUpdate",
                            headers=headers,
                            json={"requests": [rep_req]}
                        )
                        if rep_res.status_code != 200:
                            logger.warning(f"Failed to replace image {obj_id} in Google Doc {copy_document_id}: {rep_res.text}")
                        else:
                            logger.info(f"Successfully replaced image {obj_id} in Google Doc {copy_document_id}.")
                    finally:
                        try:
                            await GoogleDriveService.delete_file(access_token, temp_file_id)
                        except Exception as del_err:
                            logger.debug(f"Could not delete temp image file {temp_file_id}: {del_err}")

                except Exception as img_err:
                    logger.warning(f"Error translating image {obj_id}: {img_err}")

