import pytest
from unittest.mock import AsyncMock, patch
from app.integrations.google.ast_sync import (
    ASTBlock,
    ASTBlockType,
    GoogleDocsASTParser,
    ASTBlockMyersDiffEngine,
    ReverseIndexBatchPlanner,
    DiffOpType,
    DiffOperation,
)
from app.integrations.google.docs import GoogleDocsService
from app.documents.models import DocumentSegment


def test_ast_parser_extraction():
    sample_doc = {
        "title": "Architecture Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Overview"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 1,
                                "endIndex": 40,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "PROJECT SPECIFICATION\n", "textStyle": {"bold": True}}}],
                                    "paragraphStyle": {"namedStyleType": "TITLE"}
                                }
                            },
                            {
                                "startIndex": 40,
                                "endIndex": 90,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "1. System Architecture\n"}}],
                                    "paragraphStyle": {"namedStyleType": "HEADING_1"}
                                }
                            },
                            {
                                "startIndex": 90,
                                "endIndex": 150,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "• FastAPI Backend\n"}}],
                                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}
                                }
                            }
                        ]
                    }
                }
            }
        ]
    }

    blocks = GoogleDocsASTParser.parse_document(sample_doc)
    assert len(blocks) == 3

    assert blocks[0].block_type == ASTBlockType.TITLE
    assert blocks[0].cleaned_text == "PROJECT SPECIFICATION"
    assert blocks[0].text_style.get("bold") is True
    assert blocks[0].start_index == 1
    assert len(blocks[0].fingerprint) == 16

    assert blocks[1].block_type == ASTBlockType.HEADING_1
    assert blocks[1].cleaned_text == "1. System Architecture"
    assert blocks[1].is_heading is True

    assert blocks[2].block_type == ASTBlockType.BULLET
    assert blocks[2].cleaned_text == "• FastAPI Backend"
    assert blocks[2].is_bullet is True
    assert blocks[2].parent_heading == "1. System Architecture"


def test_myers_diff_operations():
    # Source blocks: 1 heading + 1 bullet (fastapi) + 1 newly inserted bullet (celery)
    src_h = ASTBlock(
        tab_id="t.0",
        block_index=0,
        start_index=1,
        end_index=30,
        block_type=ASTBlockType.HEADING_1,
        raw_text="1. Architecture\n",
        cleaned_text="1. Architecture",
        parent_heading="1. Architecture",
        paragraph_style={"namedStyleType": "HEADING_1"}
    )
    src_b1 = ASTBlock(
        tab_id="t.0",
        block_index=1,
        start_index=30,
        end_index=60,
        block_type=ASTBlockType.BULLET,
        raw_text="• FastAPI Backend\n",
        cleaned_text="• FastAPI Backend",
        parent_heading="1. Architecture",
        paragraph_style={"namedStyleType": "NORMAL_TEXT"}
    )
    src_b2_new = ASTBlock(
        tab_id="t.0",
        block_index=2,
        start_index=60,
        end_index=90,
        block_type=ASTBlockType.BULLET,
        raw_text="• Celery Worker\n",
        cleaned_text="• Celery Worker",
        parent_heading="1. Architecture",
        paragraph_style={"namedStyleType": "NORMAL_TEXT"}
    )

    # Target blocks: translated heading + translated fastapi + obsolete redis
    tgt_h = ASTBlock(
        tab_id="t.0",
        block_index=0,
        start_index=1,
        end_index=30,
        block_type=ASTBlockType.HEADING_1,
        raw_text="1. アーキテクチャ\n",
        cleaned_text="1. アーキテクチャ",
        parent_heading="1. アーキテクチャ",
        paragraph_style={"namedStyleType": "HEADING_1"}
    )
    tgt_b1 = ASTBlock(
        tab_id="t.0",
        block_index=1,
        start_index=30,
        end_index=60,
        block_type=ASTBlockType.BULLET,
        raw_text="• FastAPI バックエンド\n",
        cleaned_text="• FastAPI バックエンド",
        parent_heading="1. アーキテクチャ",
        paragraph_style={"namedStyleType": "NORMAL_TEXT"}
    )
    tgt_obsolete = ASTBlock(
        tab_id="t.0",
        block_index=2,
        start_index=60,
        end_index=90,
        block_type=ASTBlockType.BULLET,
        raw_text="• 削除されたRedis\n",
        cleaned_text="• 削除されたRedis",
        parent_heading="1. アーキテクチャ",
        paragraph_style={"namedStyleType": "NORMAL_TEXT"}
    )

    curr_segs = [
        DocumentSegment(id="s1", job_id="j1", segment_index=0, source_text="1. Architecture", translated_text="1. アーキテクチャ"),
        DocumentSegment(id="s2", job_id="j1", segment_index=1, source_text="• FastAPI Backend", translated_text="• FastAPI バックエンド"),
        DocumentSegment(id="s3", job_id="j1", segment_index=2, source_text="• Celery Worker", translated_text="• Celery ワーカー"),
    ]
    prev_segs = [
        DocumentSegment(id="p1", job_id="j0", segment_index=0, source_text="1. Architecture", translated_text="1. アーキテクチャ"),
        DocumentSegment(id="p2", job_id="j0", segment_index=1, source_text="• FastAPI Backend", translated_text="• FastAPI バックエンド"),
        DocumentSegment(id="p3", job_id="j0", segment_index=2, source_text="• Deleted Redis", translated_text="• 削除されたRedis"),
    ]

    engine = ASTBlockMyersDiffEngine()
    ops = engine.compute_diff(
        source_blocks=[src_h, src_b1, src_b2_new],
        target_blocks=[tgt_h, tgt_b1, tgt_obsolete],
        current_segments=curr_segs,
        previous_segments=prev_segs
    )

    # We expect:
    # 1. DELETE_BLOCK for obsolete redis
    del_op = next((o for o in ops if o.op_type == DiffOpType.DELETE_BLOCK), None)
    assert del_op is not None
    assert del_op.old_text == "• 削除されたRedis"

    # 2. INSERT_BLOCK for celery worker
    ins_op = next((o for o in ops if o.op_type == DiffOpType.INSERT_BLOCK), None)
    assert ins_op is not None
    assert ins_op.new_text == "• Celery ワーカー"


def test_reverse_index_batch_planner():
    # Verify that index-based requests are strictly ordered in descending index order
    op_insert_top = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.0",
        new_text="Top Announcement",
        target_anchor_index=1
    )
    op_insert_bottom = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.0",
        new_text="Bottom Appendix",
        target_anchor_index=500
    )
    op_update = DiffOperation(
        op_type=DiffOpType.UPDATE_TEXT,
        tab_id="t.0",
        old_text="Old Title",
        new_text="New Title"
    )

    replace_reqs, index_reqs = ReverseIndexBatchPlanner.plan_batch_updates([op_insert_top, op_insert_bottom, op_update])

    assert len(replace_reqs) == 1
    assert replace_reqs[0]["replaceAllText"]["containsText"]["text"] == "Old Title"

    assert len(index_reqs) == 2
    # First index request must be the bottom one (500)
    assert index_reqs[0]["insertText"]["location"]["index"] == 500
    # Second index request must be the top one (1)
    assert index_reqs[1]["insertText"]["location"]["index"] == 1


@pytest.mark.asyncio
async def test_e2e_google_docs_sota_ast_sync():
    """Verifies that GoogleDocsService uses SOTA AST Myers diff to perform in-place updates."""
    target_doc_mock = {
        "title": "Target Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 1,
                                "endIndex": 25,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "【プロジェクト要件仕様】\n"}}],
                                    "paragraphStyle": {"namedStyleType": "TITLE"}
                                }
                            },
                            {
                                "startIndex": 25,
                                "endIndex": 60,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "1. システムアーキテクチャの概要\n"}}],
                                    "paragraphStyle": {"namedStyleType": "HEADING_1"}
                                }
                            }
                        ]
                    }
                }
            }
        ]
    }

    prev_heading = DocumentSegment(
        id="p1", job_id="j0", segment_index=0,
        location_json='{"tab_id": "t.0"}',
        source_text="1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG",
        translated_text="1. システムアーキテクチャの概要"
    )

    # Current job:
    # 1. New text at top
    c_top = DocumentSegment(
        id="c0", job_id="j1", segment_index=0,
        location_json='{"tab_id": "t.0"}',
        source_text="đây là text dùng để test",
        translated_text="これはテスト用テキストです"
    )
    # 2. Unchanged title
    c_title = DocumentSegment(
        id="c1", job_id="j1", segment_index=1,
        location_json='{"tab_id": "t.0"}',
        source_text="ĐẶC TẢ YÊU CẦU DỰ ÁN",
        translated_text="【プロジェクト要件仕様】"
    )
    # 3. Modified heading with appended text
    c_heading = DocumentSegment(
        id="c2", job_id="j1", segment_index=2,
        location_json='{"tab_id": "t.0"}',
        source_text="1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG đây là text dùng để test",
        translated_text="1. システムアーキテクチャの概要 これはテスト用テキストです"
    )

    with patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=target_doc_mock):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"replies": []}

            await GoogleDocsService.apply_smart_delta_sync_to_existing_doc(
                access_token="test_token",
                target_document_id="target-doc-123",
                segments=[c_top, c_title, c_heading],
                previous_segments=[prev_heading],
                is_mock=False
            )

            assert mock_post.called
            all_batches = [call.kwargs.get("json", {}).get("requests", []) for call in mock_post.call_args_list]
            flattened = [r for batch in all_batches for r in batch]

            # 1. replaceAllText for modified heading
            rep_op = next((
                r for r in flattened
                if "replaceAllText" in r and r["replaceAllText"]["containsText"]["text"] == "1. システムアーキテクチャの概要"
            ), None)
            assert rep_op is not None
            assert rep_op["replaceAllText"]["replaceText"] == "1. システムアーキテクチャの概要 これはテスト用テキストです"

            # 2. insertText for top text anchored at index 1
            ins_op = next((r for r in flattened if "insertText" in r), None)
            assert ins_op is not None
            assert "これはテスト用テキストです" in ins_op["insertText"]["text"]
            assert ins_op["insertText"]["location"]["index"] == 1


def test_ast_parser_image_extraction():
    """Verifies that GoogleDocsASTParser correctly identifies inline images and metadata."""
    sample_doc_with_images = {
        "title": "Cloud Architecture",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.ixntlmjqdi80", "title": "Diagrams"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 1,
                                "endIndex": 40,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:\n"}}],
                                    "paragraphStyle": {"namedStyleType": "HEADING_1"}
                                }
                            },
                            {
                                "startIndex": 40,
                                "endIndex": 42,
                                "paragraph": {
                                    "elements": [
                                        {"startIndex": 40, "endIndex": 41, "inlineObjectElement": {"inlineObjectId": "kix.diagram123"}},
                                        {"startIndex": 41, "endIndex": 42, "textRun": {"content": "\n"}}
                                    ],
                                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}
                                }
                            },
                            {
                                "startIndex": 42,
                                "endIndex": 80,
                                "paragraph": {
                                    "elements": [{"textRun": {"content": "3. Security Principles\n"}}],
                                    "paragraphStyle": {"namedStyleType": "HEADING_1"}
                                }
                            }
                        ]
                    },
                    "inlineObjects": {
                        "kix.diagram123": {
                            "objectId": "kix.diagram123",
                            "inlineObjectProperties": {
                                "embeddedObject": {
                                    "imageProperties": {
                                        "contentUri": "https://lh3.googleusercontent.com/docs/test_image.png"
                                    },
                                    "size": {
                                        "height": {"magnitude": 250, "unit": "PT"},
                                        "width": {"magnitude": 500, "unit": "PT"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        ]
    }

    blocks = GoogleDocsASTParser.parse_document(sample_doc_with_images)
    assert len(blocks) == 3

    # Heading 1
    assert blocks[0].block_type == ASTBlockType.HEADING_1
    assert blocks[0].cleaned_text == "2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:"

    # Image block
    img_b = blocks[1]
    assert img_b.block_type == ASTBlockType.IMAGE
    assert img_b.parent_heading == "2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:"
    assert img_b.metadata["inline_object_id"] == "kix.diagram123"
    assert img_b.metadata["content_uri"] == "https://lh3.googleusercontent.com/docs/test_image.png"
    assert img_b.metadata["is_alone_in_paragraph"] is True
    assert img_b.metadata["paragraph_start_index"] == 40
    assert img_b.metadata["paragraph_end_index"] == 42
    assert img_b.start_index == 40
    assert img_b.end_index == 42

    # Heading 2
    assert blocks[2].block_type == ASTBlockType.HEADING_1
    assert blocks[2].cleaned_text == "3. Security Principles"


def test_myers_diff_image_deletion_and_insertion():
    """Verifies that Myers Diff accurately detects deleted images and newly inserted images."""
    # Target doc: Has Heading 2 + Diagram 1 + Heading 3 + Diagram 2
    tgt_h2 = ASTBlock(
        tab_id="t.1", block_index=0, start_index=1, end_index=40,
        block_type=ASTBlockType.HEADING_1, raw_text="2. CLOUD PLATFORM アーキテクチャ図：\n",
        cleaned_text="2. CLOUD PLATFORM アーキテクチャ図：", parent_heading="2. CLOUD PLATFORM アーキテクチャ図："
    )
    tgt_img1 = ASTBlock(
        tab_id="t.1", block_index=1, start_index=40, end_index=42,
        block_type=ASTBlockType.IMAGE, raw_text="[IMAGE: kix.diag1]",
        cleaned_text="[IMAGE: kix.diag1]", parent_heading="2. CLOUD PLATFORM アーキテクチャ図：",
        metadata={"inline_object_id": "kix.diag1", "paragraph_start_index": 40, "paragraph_end_index": 42, "is_alone_in_paragraph": True}
    )
    tgt_h3 = ASTBlock(
        tab_id="t.1", block_index=2, start_index=42, end_index=80,
        block_type=ASTBlockType.HEADING_1, raw_text="3. セキュリティ原則\n",
        cleaned_text="3. セキュリティ原則", parent_heading="3. セキュリティ原則"
    )

    # Source doc:
    # 1. Heading 2 (unchanged)
    # 2. (Diagram 1 was DELETED in source!)
    # 3. Heading 3 (unchanged)
    # 4. Diagram 2 (NEWLY ADDED in source under Heading 3!)
    src_h2 = ASTBlock(
        tab_id="t.1", block_index=0, start_index=1, end_index=40,
        block_type=ASTBlockType.HEADING_1, raw_text="2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:\n",
        cleaned_text="2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:", parent_heading="2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:"
    )
    src_h3 = ASTBlock(
        tab_id="t.1", block_index=1, start_index=40, end_index=80,
        block_type=ASTBlockType.HEADING_1, raw_text="3. NGUYÊN TẮC BẢO MẬT\n",
        cleaned_text="3. NGUYÊN TẮC BẢO MẬT", parent_heading="3. NGUYÊN TẮC BẢO MẬT"
    )
    src_img_new = ASTBlock(
        tab_id="t.1", block_index=2, start_index=80, end_index=82,
        block_type=ASTBlockType.IMAGE, raw_text="[IMAGE: kix.new_diag2]",
        cleaned_text="[IMAGE: kix.new_diag2]", parent_heading="3. NGUYÊN TẮC BẢO MẬT",
        metadata={
            "inline_object_id": "kix.new_diag2",
            "content_uri": "https://lh3.googleusercontent.com/docs/new.png",
            "size": {"width": {"magnitude": 400, "unit": "PT"}, "height": {"magnitude": 200, "unit": "PT"}},
            "is_alone_in_paragraph": True,
            "paragraph_start_index": 80,
            "paragraph_end_index": 82
        }
    )

    curr_segs = [
        DocumentSegment(id="s1", job_id="j1", segment_index=0, source_text="2. SƠ ĐỒ KIẾN TRÚC CLOUD PLATFORM:", translated_text="2. CLOUD PLATFORM アーキテクチャ図："),
        DocumentSegment(id="s2", job_id="j1", segment_index=1, source_text="3. NGUYÊN TẮC BẢO MẬT", translated_text="3. セキュリティ原則"),
    ]

    engine = ASTBlockMyersDiffEngine()
    ops = engine.compute_diff(
        source_blocks=[src_h2, src_h3, src_img_new],
        target_blocks=[tgt_h2, tgt_img1, tgt_h3],
        current_segments=curr_segs
    )

    # 1. Target Diagram 1 must be marked DELETE_BLOCK
    del_ops = [o for o in ops if o.op_type == DiffOpType.DELETE_BLOCK and o.target_block.block_type == ASTBlockType.IMAGE]
    assert len(del_ops) == 1
    assert del_ops[0].target_block.metadata["inline_object_id"] == "kix.diag1"

    # 2. Source Diagram 2 must be marked INSERT_BLOCK
    ins_ops = [o for o in ops if o.op_type == DiffOpType.INSERT_BLOCK and o.source_block.block_type == ASTBlockType.IMAGE]
    assert len(ins_ops) == 1
    assert ins_ops[0].source_block.metadata["inline_object_id"] == "kix.new_diag2"
    assert ins_ops[0].target_anchor_index == tgt_h3.end_index  # Anchored after Heading 3 in target!


def test_reverse_index_planner_image_mutations():
    """Verifies that deleteContentRange cleanly deletes paragraph range and insertInlineImage is planned."""
    del_img_block = ASTBlock(
        tab_id="t.1", block_index=1, start_index=100, end_index=102,
        block_type=ASTBlockType.IMAGE, raw_text="[IMAGE: kix.del]",
        cleaned_text="[IMAGE: kix.del]",
        metadata={
            "inline_object_id": "kix.del",
            "paragraph_start_index": 100,
            "paragraph_end_index": 102,
            "is_alone_in_paragraph": True,
            "is_last_body_element": False
        }
    )
    ins_img_block = ASTBlock(
        tab_id="t.1", block_index=0, start_index=50, end_index=52,
        block_type=ASTBlockType.IMAGE, raw_text="[IMAGE: kix.ins]",
        cleaned_text="[IMAGE: kix.ins]",
        metadata={
            "inline_object_id": "kix.ins",
            "content_uri": "https://lh3.googleusercontent.com/docs/insert.png",
            "size": {"width": {"magnitude": 450, "unit": "PT"}, "height": {"magnitude": 250, "unit": "PT"}}
        }
    )

    del_op = DiffOperation(
        op_type=DiffOpType.DELETE_BLOCK,
        tab_id="t.1",
        target_block=del_img_block,
        metadata=del_img_block.metadata
    )
    ins_op = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.1",
        source_block=ins_img_block,
        target_anchor_index=50,
        metadata={
            "image_uri": "https://lh3.googleusercontent.com/d/temp_drive_123",
            "size": {"width": {"magnitude": 450, "unit": "PT"}, "height": {"magnitude": 250, "unit": "PT"}}
        }
    )

    replace_reqs, index_reqs = ReverseIndexBatchPlanner.plan_batch_updates([del_op, ins_op])

    assert len(replace_reqs) == 0
    # Expected index requests:
    # 1. deleteContentRange at index 100 (range 100..102, deleting newline cleanly)
    # 2. insertText at index 50
    # 3. insertInlineImage at index 50
    assert len(index_reqs) == 3

    # Sorted descending by index: first is deletion at 100
    assert "deleteContentRange" in index_reqs[0]
    del_range = index_reqs[0]["deleteContentRange"]["range"]
    assert del_range["startIndex"] == 100
    assert del_range["endIndex"] == 102
    assert del_range["tabId"] == "t.1"

    # Second & Third are insertion at index 50
    assert "insertText" in index_reqs[1]
    assert index_reqs[1]["insertText"]["location"]["index"] == 50

    assert "insertInlineImage" in index_reqs[2]
    img_req = index_reqs[2]["insertInlineImage"]
    assert img_req["location"]["index"] == 50
    assert img_req["uri"] == "https://lh3.googleusercontent.com/d/temp_drive_123"
    assert img_req["objectSize"]["width"]["magnitude"] == 450

