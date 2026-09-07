"""
Comprehensive unit and integration test suite for Google Slides AST Myers Diff & Scoped In-Place Sync Engine.
Validates:
1. GoogleSlidesASTParser (shapes, tables, images, speaker notes, transforms, fingerprints).
2. SlideMyersDiffEngine (LCS sequence diff, NO_CHANGE, UPDATE_SLIDE, INSERT_SLIDE, DELETE_SLIDE, sub-diffs).
3. SlideReverseIndexBatchPlanner (descending deletions, scoped replaceAllText with pageObjectIds, native replaceImage).
4. GoogleSlidesService (parse_segments with tables, apply_translations_to_copy with slide_id, apply_smart_slide_sync).
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.integrations.google.slides_ast_sync import (
    GoogleSlidesASTParser,
    SlideASTNode,
    SlideElementASTNode,
    SlideElementType,
    SlideDiffOp,
    SlideDiffOpType,
    SlideMyersDiffEngine,
    SlideReverseIndexBatchPlanner,
)
from app.integrations.google.slides import GoogleSlidesService


MOCK_PRESENTATION_RICH = {
    "presentationId": "pres_rich_123",
    "title": "Cloud Architecture & Security",
    "slides": [
        {
            "objectId": "slide_1",
            "pageElements": [
                {
                    "objectId": "shape_title_1",
                    "size": {"width": {"magnitude": 400.0, "unit": "PT"}, "height": {"magnitude": 50.0, "unit": "PT"}},
                    "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 30.0},
                    "shape": {
                        "shapeType": "TEXT_BOX",
                        "text": {
                            "textElements": [
                                {"startIndex": 0, "endIndex": 15, "textRun": {"content": "クラウド設計原則\n"}}
                            ]
                        }
                    }
                },
                {
                    "objectId": "img_arch_1",
                    "size": {"width": {"magnitude": 300.0, "unit": "PT"}, "height": {"magnitude": 200.0, "unit": "PT"}},
                    "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 100.0},
                    "image": {
                        "contentUrl": "https://lh3.googleusercontent.com/test_img_1.png"
                    }
                }
            ],
            "slideProperties": {
                "notesPage": {
                    "objectId": "notes_page_1",
                    "pageElements": [
                        {
                            "objectId": "notes_shape_1",
                            "shape": {
                                "shapeType": "BODY",
                                "text": {
                                    "textElements": [
                                        {"textRun": {"content": "発表時の補足説明：セキュリティ要件を強調すること。\n"}}
                                    ]
                                }
                            }
                        }
                    ]
                }
            }
        },
        {
            "objectId": "slide_2",
            "pageElements": [
                {
                    "objectId": "table_perf_2",
                    "size": {"width": {"magnitude": 500.0, "unit": "PT"}, "height": {"magnitude": 150.0, "unit": "PT"}},
                    "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 40.0, "translateY": 60.0},
                    "table": {
                        "rows": 2,
                        "columns": 2,
                        "tableRows": [
                            {
                                "tableCells": [
                                    {"text": {"textElements": [{"textRun": {"content": "サービス名\n"}}]}},
                                    {"text": {"textElements": [{"textRun": {"content": "応答時間\n"}}]}}
                                ]
                            },
                            {
                                "tableCells": [
                                    {"text": {"textElements": [{"textRun": {"content": "API Gateway\n"}}]}},
                                    {"text": {"textElements": [{"textRun": {"content": "15ms以下\n"}}]}}
                                ]
                            }
                        ]
                    }
                }
            ],
            "slideProperties": {
                "notesPage": {
                    "objectId": "notes_page_2",
                    "pageElements": []
                }
            }
        }
    ]
}


def test_slide_ast_parser_extracts_shapes_tables_images_and_notes():
    """Verifies that GoogleSlidesASTParser extracts shapes, tables, images, and notes accurately."""
    slides = GoogleSlidesASTParser.parse_presentation(MOCK_PRESENTATION_RICH)
    assert len(slides) == 2

    # Slide 1 Checks
    s1 = slides[0]
    assert s1.slide_id == "slide_1"
    assert s1.slide_index == 0
    assert "クラウド設計原則" in s1.text_signature
    assert s1.notes_page_id == "notes_page_1"
    assert len(s1.notes_elements) >= 1
    assert "セキュリティ要件を強調すること" in s1.notes_elements[0].plain_text
    assert len(s1.elements) == 2

    # Shape element
    el_shape = s1.elements[0]
    assert el_shape.element_id == "shape_title_1"
    assert el_shape.element_type == SlideElementType.SHAPE
    assert "クラウド設計原則" in el_shape.plain_text
    assert el_shape.bounding_box == (50.0, 30.0, 400.0, 50.0)

    # Image element
    el_img = s1.elements[1]
    assert el_img.element_id == "img_arch_1"
    assert el_img.element_type == SlideElementType.IMAGE
    assert el_img.image_url == "https://lh3.googleusercontent.com/test_img_1.png"

    # Slide 2 Checks (Table)
    s2 = slides[1]
    assert s2.slide_id == "slide_2"
    assert len(s2.elements) == 1
    el_table = s2.elements[0]
    assert el_table.element_id == "table_perf_2"
    assert el_table.element_type == SlideElementType.TABLE
    assert len(el_table.table_cells) == 4
    assert any("API Gateway" in c["text"] for c in el_table.table_cells)
    assert any("応答時間" in c["text"] for c in el_table.table_cells)


def test_slide_myers_diff_no_change_when_identical():
    """Verifies that comparing two identical presentations returns NO_CHANGE for all slides."""
    slides_a = GoogleSlidesASTParser.parse_presentation(MOCK_PRESENTATION_RICH)
    slides_b = GoogleSlidesASTParser.parse_presentation(MOCK_PRESENTATION_RICH)

    diff_ops = SlideMyersDiffEngine.diff_slides(slides_a, slides_b)
    assert len(diff_ops) == 2
    for op in diff_ops:
        assert op.op_type == SlideDiffOpType.NO_CHANGE


def test_slide_myers_diff_insert_and_delete_detection():
    """Verifies that inserting and deleting slides is accurately detected by Myers LCS diff."""
    slides_orig = GoogleSlidesASTParser.parse_presentation(MOCK_PRESENTATION_RICH)

    # Synthetic target with 1 slide deleted and 1 slide added
    target_slides = [
        slides_orig[0],  # Keeps slide 1
        SlideASTNode(
            slide_id="slide_new_extra",
            slide_index=1,
            text_signature="Extra slide",
            structure_hash="hash_extra",
            semantic_fingerprint="fp_extra_unique"
        )
    ]

    diff_ops = SlideMyersDiffEngine.diff_slides(
        source_slides=slides_orig,
        target_slides=target_slides
    )

    op_types = [op.op_type for op in diff_ops]
    assert SlideDiffOpType.NO_CHANGE in op_types
    assert SlideDiffOpType.UPDATE_SLIDE in op_types or SlideDiffOpType.INSERT_SLIDE in op_types or SlideDiffOpType.DELETE_SLIDE in op_types


def test_slide_myers_diff_sub_diff_text_and_image():
    """Verifies that element-level text modifications on a slide generate UPDATE_SLIDE with mutations."""
    slides_src = GoogleSlidesASTParser.parse_presentation(MOCK_PRESENTATION_RICH)

    # Create modified copy of presentation
    modified_pres = json.loads(json.dumps(MOCK_PRESENTATION_RICH))
    modified_pres["slides"][0]["pageElements"][0]["shape"]["text"]["textElements"][0]["textRun"]["content"] = "システム要件定義書\n"
    slides_tgt = GoogleSlidesASTParser.parse_presentation(modified_pres)

    diff_ops = SlideMyersDiffEngine.diff_slides(slides_src, slides_tgt)
    update_ops = [op for op in diff_ops if op.op_type == SlideDiffOpType.UPDATE_SLIDE]
    assert len(update_ops) >= 1
    assert len(update_ops[0].element_diffs) >= 1


def test_slide_reverse_index_batch_planner_descending_deletions():
    """Verifies that deleteObject operations are ordered in descending slide index to eliminate index shift drift."""
    diff_ops = [
        SlideDiffOp(op_type=SlideDiffOpType.DELETE_SLIDE, target_slide_id="slide_idx_1", target_slide_index=1),
        SlideDiffOp(op_type=SlideDiffOpType.DELETE_SLIDE, target_slide_id="slide_idx_5", target_slide_index=5),
        SlideDiffOp(op_type=SlideDiffOpType.DELETE_SLIDE, target_slide_id="slide_idx_3", target_slide_index=3),
    ]

    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(diff_ops, segments=[])
    del_ops = [r["deleteObject"]["objectId"] for r in batch if "deleteObject" in r]
    # Expect order: slide_idx_5, slide_idx_3, slide_idx_1
    assert del_ops == ["slide_idx_5", "slide_idx_3", "slide_idx_1"]


def test_slide_reverse_index_batch_planner_scoped_replacements():
    """Verifies that replaceAllText requests are strictly scoped with pageObjectIds: [slide_id]."""
    slides = GoogleSlidesASTParser.parse_presentation(MOCK_PRESENTATION_RICH)
    diff_ops = [
        SlideDiffOp(
            op_type=SlideDiffOpType.NO_CHANGE,
            target_slide_id="slide_1",
            target_slide_index=0,
            target_slide=slides[0]
        ),
        SlideDiffOp(
            op_type=SlideDiffOpType.NO_CHANGE,
            target_slide_id="slide_2",
            target_slide_index=1,
            target_slide=slides[1]
        )
    ]

    segments = [
        {
            "source_text": "クラウド設計原則",
            "translated_text": "Cloud Design Principles",
            "location": {"type": "gslide_shape", "slide_id": "slide_1", "slide_num": 1}
        },
        {
            "source_text": "セキュリティ要件を強調すること。",
            "translated_text": "Emphasize security requirements.",
            "location": {"type": "gslide_note", "slide_id": "slide_1", "notes_page_id": "notes_page_1", "slide_num": 1}
        },
        {
            "source_text": "API Gateway",
            "translated_text": "Cổng API Gateway",
            "location": {"type": "gslide_table_cell", "slide_id": "slide_2", "slide_num": 2}
        }
    ]

    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(diff_ops, segments=segments)
    replace_ops = [r["replaceAllText"] for r in batch if "replaceAllText" in r]

    assert len(replace_ops) >= 3

    # Check slide 1 shape replacement has pageObjectIds: ['slide_1']
    slide1_req = next(r for r in replace_ops if r["containsText"]["text"] == "クラウド設計原則")
    assert slide1_req["replaceText"] == "Cloud Design Principles"
    assert slide1_req["pageObjectIds"] == ["slide_1"]

    # Check slide 1 note replacement has pageObjectIds: ['notes_page_1']
    note_req = next(r for r in replace_ops if r["containsText"]["text"] == "セキュリティ要件を強調すること。")
    assert note_req["replaceText"] == "Emphasize security requirements."
    assert note_req["pageObjectIds"] == ["notes_page_1"]

    # Check slide 2 table cell replacement has pageObjectIds: ['slide_2']
    slide2_req = next(r for r in replace_ops if r["containsText"]["text"] == "API Gateway")
    assert slide2_req["replaceText"] == "Cổng API Gateway"
    assert slide2_req["pageObjectIds"] == ["slide_2"]


def test_slide_native_replace_image_planner():
    """Verifies that native replaceImage requests are generated with imageObjectId and CENTER_CROP."""
    image_replacements = {
        "img_arch_1": "https://lh3.googleusercontent.com/d/new_translated_img_123"
    }

    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(
        diff_ops=[],
        segments=[],
        image_replacements=image_replacements
    )

    img_ops = [r["replaceImage"] for r in batch if "replaceImage" in r]
    assert len(img_ops) == 1
    assert img_ops[0]["imageObjectId"] == "img_arch_1"
    assert img_ops[0]["url"] == "https://lh3.googleusercontent.com/d/new_translated_img_123"
    assert img_ops[0]["imageReplaceMethod"] == "CENTER_CROP"


def test_google_slides_service_parse_segments_with_tables():
    """Verifies that GoogleSlidesService.parse_segments extracts shapes, tables, and notes into ParsedSegment objects."""
    segments, meta = GoogleSlidesService.parse_segments(MOCK_PRESENTATION_RICH, translate_notes=True)

    assert meta["total_slides"] == 2
    assert meta["total_shapes"] == 1
    assert meta["total_tables"] == 4  # 4 cells in the table
    assert meta["total_notes"] == 1
    assert meta["total_segments"] == 6

    # Verify table segment location metadata
    table_segs = [s for s in segments if s.location.get("type") == "gslide_table_cell"]
    assert len(table_segs) == 4
    assert table_segs[0].location["slide_id"] == "slide_2"
    assert "row" in table_segs[0].location
    assert "col" in table_segs[0].location


@pytest.mark.asyncio
async def test_apply_smart_slide_sync_orchestration_mock():
    """Verifies that GoogleSlidesService.apply_smart_slide_sync_to_existing_presentation runs mock and live diffs cleanly."""
    res_mock = await GoogleSlidesService.apply_smart_slide_sync_to_existing_presentation(
        access_token="test_token",
        target_presentation_id="mock_target_123",
        segments=[],
        is_mock=True
    )
    assert res_mock["status"] == "success"

    # Test with mocked API presentation calls
    with patch.object(GoogleSlidesService, "get_presentation", new_callable=AsyncMock, return_value=MOCK_PRESENTATION_RICH):
        segments, _ = GoogleSlidesService.parse_segments(MOCK_PRESENTATION_RICH)
        for s in segments:
            s.translated_text = f"Translated: {s.source_text}"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            result = await GoogleSlidesService.apply_smart_slide_sync_to_existing_presentation(
                access_token="test_token",
                target_presentation_id="pres_rich_123",
                segments=segments,
                source_presentation_id="pres_rich_123",
                translate_images=False,
                is_mock=False
            )

            assert result["status"] == "success"
            assert result["diff_operations"] == 2
            assert result["batch_requests_executed"] >= 1


def test_bilingual_cross_language_slide_alignment_with_insertion():
    """Verifies that slides are aligned by ID & structure across different languages and new slides are replicated."""
    # Target in Japanese (3 slides: slide_0, slide_1, slide_table)
    tgt_slides = [
        SlideASTNode(slide_id="slide_0", slide_index=0, text_signature="マイクロサービスの近代化計画", structure_hash="struct_title"),
        SlideASTNode(slide_id="slide_1", slide_index=1, text_signature="システム構成図", structure_hash="struct_arch"),
        SlideASTNode(slide_id="slide_table", slide_index=2, text_signature="パフォーマンス指標とSLA", structure_hash="struct_table"),
    ]

    # Source in Vietnamese (4 slides: slide_0, slide_1, NEW slide_diagram_2, slide_table)
    new_slide = SlideASTNode(
        slide_id="slide_diagram_2",
        slide_index=2,
        text_signature="Sơ đồ chi tiết luồng xử lý",
        structure_hash="struct_flow",
        elements=[
            SlideElementASTNode(
                element_id="sh_flow_1",
                element_type=SlideElementType.SHAPE,
                plain_text="Luồng xử lý bất đồng bộ",
                size={"width": {"magnitude": 400, "unit": "PT"}, "height": {"magnitude": 50, "unit": "PT"}},
                transform={"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 50, "unit": "PT"}
            ),
            SlideElementASTNode(
                element_id="img_flow_1",
                element_type=SlideElementType.IMAGE,
                image_url="https://example.com/diagram2.png",
                size={"width": {"magnitude": 500, "unit": "PT"}, "height": {"magnitude": 250, "unit": "PT"}},
                transform={"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 120, "unit": "PT"}
            )
        ]
    )

    src_slides = [
        SlideASTNode(slide_id="slide_0", slide_index=0, text_signature="Kế hoạch hiện đại hóa microservices", structure_hash="struct_title"),
        SlideASTNode(slide_id="slide_1", slide_index=1, text_signature="Sơ đồ cấu hình hệ thống", structure_hash="struct_arch"),
        new_slide,
        SlideASTNode(slide_id="slide_table", slide_index=3, text_signature="Chỉ số hiệu năng và SLA", structure_hash="struct_table"),
    ]

    diff_ops = SlideMyersDiffEngine.diff_slides(src_slides, tgt_slides)

    # Asserts
    assert len(diff_ops) == 4
    # slide_0 matches slide_0
    assert diff_ops[0].source_slide_id == "slide_0" and diff_ops[0].target_slide_id == "slide_0"
    # slide_1 matches slide_1
    assert diff_ops[1].source_slide_id == "slide_1" and diff_ops[1].target_slide_id == "slide_1"
    # slide_table matches slide_table
    assert diff_ops[2].source_slide_id == "slide_table" and diff_ops[2].target_slide_id == "slide_table"
    # new slide is INSERT_SLIDE
    assert diff_ops[3].op_type == SlideDiffOpType.INSERT_SLIDE
    assert diff_ops[3].source_slide_id == "slide_diagram_2"
    assert diff_ops[3].source_slide_index == 2

    # Verify batch planning replicates full content
    segments = [
        {"source_text": "Luồng xử lý bất đồng bộ", "translated_text": "非同期処理フロー", "location": {"slide_id": "slide_diagram_2"}}
    ]
    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(diff_ops, segments=segments)

    create_slides = [r for r in batch if "createSlide" in r]
    assert len(create_slides) == 1
    assert create_slides[0]["createSlide"]["insertionIndex"] == 2

    create_shapes = [r for r in batch if "createShape" in r]
    assert len(create_shapes) == 1

    insert_texts = [r for r in batch if "insertText" in r]
    assert len(insert_texts) == 1
    assert insert_texts[0]["insertText"]["text"] == "非同期処理フロー"

    create_images = [r for r in batch if "createImage" in r]
    assert len(create_images) == 1
    assert create_images[0]["createImage"]["url"] == "https://example.com/diagram2.png"


@pytest.mark.asyncio
async def test_translate_embedded_images_in_presentation():
    """Verifies that translate_embedded_images_in_presentation detects images, translates via OCR,
    uploads to Drive, and issues replaceImage requests."""
    fake_presentation = {
        "presentationId": "pres_123",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "img_arch_01",
                        "image": {
                            "contentUrl": "https://example.com/slide_img.png"
                        }
                    }
                ]
            }
        ]
    }

    orig_bytes = b"ORIGINAL_DIAGRAM_IMAGE_BYTES_PADDING_PADDING_MORE_THAN_100_CHARS_0123456789_ABCDEFGHIJ_EXTRA_PADDING_1234567890"
    trans_bytes = b"TRANSLATED_DIAGRAM_IMAGE_BYTES_PADDING_PADDING_MORE_THAN_100_CHARS_0123456789_ABCDEFGHIJ_EXTRA_PADDING_1234567890"

    with patch.object(GoogleSlidesService, "get_presentation", new_callable=AsyncMock, return_value=fake_presentation):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = orig_bytes

            with patch("app.documents.ocr.image_translator.image_translator.process_image", new_callable=AsyncMock, return_value=trans_bytes):
                with patch("app.integrations.google.drive.GoogleDriveService.upload_file", new_callable=AsyncMock, return_value={"id": "drive_img_999"}) as mock_upload:
                    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                        mock_post.return_value.status_code = 200
                        mock_post.return_value.text = "{}"

                        result = await GoogleSlidesService.translate_embedded_images_in_presentation(
                            access_token="test_token",
                            presentation_id="pres_123",
                            source_lang="vi",
                            target_lang="ja",
                            is_mock=False
                        )

                        assert result["status"] == "success"
                        assert result["images_translated"] == 1
                        assert mock_upload.called
                        assert mock_post.called
                        # Verify replaceImage request was sent
                        post_calls = mock_post.call_args_list
                        batch_update_call = next(c for c in post_calls if "batchUpdate" in c.args[0])
                        reqs = batch_update_call.kwargs["json"]["requests"]
                        assert len(reqs) == 1
                        assert reqs[0]["replaceImage"]["imageObjectId"] == "img_arch_01"
                        assert "drive_img_999" in reqs[0]["replaceImage"]["url"]


def test_sub_diff_and_planner_add_text_to_existing_slide():
    """Verifies that adding a new text box/shape to an existing slide produces createShape + insertText in batch updates."""
    # Target presentation has only title shape
    tgt_pres = {
        "presentationId": "pres_tgt",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "shape_title_1",
                        "size": {"width": {"magnitude": 400.0, "unit": "PT"}, "height": {"magnitude": 50.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 30.0},
                        "shape": {
                            "shapeType": "TEXT_BOX",
                            "text": {"textElements": [{"textRun": {"content": "タイトル\n"}}]}
                        }
                    }
                ]
            }
        ]
    }

    # Source presentation has title shape AND a newly added text box
    src_pres = json.loads(json.dumps(tgt_pres))
    src_pres["slides"][0]["pageElements"].append({
        "objectId": "shape_new_text_box",
        "size": {"width": {"magnitude": 300.0, "unit": "PT"}, "height": {"magnitude": 60.0, "unit": "PT"}},
        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 120.0},
        "shape": {
            "shapeType": "TEXT_BOX",
            "text": {"textElements": [{"textRun": {"content": "新規追加テキスト\n"}}]}
        }
    })

    src_slides = GoogleSlidesASTParser.parse_presentation(src_pres)
    tgt_slides = GoogleSlidesASTParser.parse_presentation(tgt_pres)

    diff_ops = SlideMyersDiffEngine.diff_slides(src_slides, tgt_slides)
    assert len(diff_ops) == 1
    op = diff_ops[0]
    assert op.op_type == SlideDiffOpType.UPDATE_SLIDE
    assert op.target_slide_id == "slide_1"

    insert_diffs = [ed for ed in op.element_diffs if ed.get("type") == "insert_element"]
    assert len(insert_diffs) == 1
    assert insert_diffs[0]["source_element"].element_id == "shape_new_text_box"

    # Segments containing translation
    segments = [
        {"source_text": "タイトル", "translated_text": "Tiêu đề", "location": {"type": "gslide_shape", "slide_id": "slide_1"}},
        {"source_text": "新規追加テキスト", "translated_text": "Văn bản mới được thêm", "location": {"type": "gslide_shape", "slide_id": "slide_1"}}
    ]

    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(diff_ops, segments=segments)

    # Check createShape and insertText exist in batch
    create_shapes = [r["createShape"] for r in batch if "createShape" in r]
    assert len(create_shapes) == 1
    new_sh_id = create_shapes[0]["objectId"]
    assert create_shapes[0]["elementProperties"]["pageObjectId"] == "slide_1"

    insert_texts = [r["insertText"] for r in batch if "insertText" in r]
    assert any(it["objectId"] == new_sh_id and it["text"] == "Văn bản mới được thêm" for it in insert_texts)


def test_sub_diff_and_planner_delete_image_from_existing_slide():
    """Verifies that removing an image from an existing slide produces deleteObject in batch updates and avoids replaceImage."""
    # Source presentation has only title shape (image was deleted by user)
    src_pres = {
        "presentationId": "pres_src",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "shape_title_1",
                        "size": {"width": {"magnitude": 400.0, "unit": "PT"}, "height": {"magnitude": 50.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 30.0},
                        "shape": {
                            "shapeType": "TEXT_BOX",
                            "text": {"textElements": [{"textRun": {"content": "タイトル\n"}}]}
                        }
                    }
                ]
            }
        ]
    }

    # Target presentation still has the old image
    tgt_pres = json.loads(json.dumps(src_pres))
    tgt_pres["slides"][0]["pageElements"].append({
        "objectId": "img_old_diagram",
        "size": {"width": {"magnitude": 300.0, "unit": "PT"}, "height": {"magnitude": 200.0, "unit": "PT"}},
        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 100.0},
        "image": {"contentUrl": "https://example.com/old_diagram.png"}
    })

    src_slides = GoogleSlidesASTParser.parse_presentation(src_pres)
    tgt_slides = GoogleSlidesASTParser.parse_presentation(tgt_pres)

    diff_ops = SlideMyersDiffEngine.diff_slides(src_slides, tgt_slides)
    assert len(diff_ops) == 1
    op = diff_ops[0]
    assert op.op_type == SlideDiffOpType.UPDATE_SLIDE

    delete_diffs = [ed for ed in op.element_diffs if ed.get("type") == "delete_element"]
    assert len(delete_diffs) == 1
    assert delete_diffs[0]["target_element_id"] == "img_old_diagram"

    # Planner should output deleteObject for img_old_diagram
    # And even if image_replacements has img_old_diagram, it must NOT call replaceImage
    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(
        diff_ops,
        segments=[],
        image_replacements={"img_old_diagram": "https://example.com/new_translated.png"}
    )

    delete_objects = [r["deleteObject"]["objectId"] for r in batch if "deleteObject" in r]
    assert "img_old_diagram" in delete_objects

    replace_images = [r["replaceImage"]["imageObjectId"] for r in batch if "replaceImage" in r]
    assert "img_old_diagram" not in replace_images


def test_sub_diff_and_planner_add_text_and_delete_image_simultaneously():
    """Verifies that simultaneous element addition and deletion on the same slide orders deleteObject before createShape."""
    # Target presentation has shape A and Image B
    tgt_pres = {
        "presentationId": "pres_simul",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "shape_a",
                        "size": {"width": {"magnitude": 100.0, "unit": "PT"}, "height": {"magnitude": 30.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 10.0, "translateY": 10.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "Text A\n"}}]}}
                    },
                    {
                        "objectId": "img_b",
                        "size": {"width": {"magnitude": 200.0, "unit": "PT"}, "height": {"magnitude": 150.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 10.0, "translateY": 50.0},
                        "image": {"contentUrl": "https://example.com/b.png"}
                    }
                ]
            }
        ]
    }

    # Source presentation kept shape A, removed Image B, and added shape C
    src_pres = {
        "presentationId": "pres_simul",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "shape_a",
                        "size": {"width": {"magnitude": 100.0, "unit": "PT"}, "height": {"magnitude": 30.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 10.0, "translateY": 10.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "Text A\n"}}]}}
                    },
                    {
                        "objectId": "shape_c_new",
                        "size": {"width": {"magnitude": 150.0, "unit": "PT"}, "height": {"magnitude": 40.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 10.0, "translateY": 80.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "Text C New\n"}}]}}
                    }
                ]
            }
        ]
    }

    src_slides = GoogleSlidesASTParser.parse_presentation(src_pres)
    tgt_slides = GoogleSlidesASTParser.parse_presentation(tgt_pres)

    diff_ops = SlideMyersDiffEngine.diff_slides(src_slides, tgt_slides)
    assert len(diff_ops) == 1
    op = diff_ops[0]
    assert op.op_type == SlideDiffOpType.UPDATE_SLIDE

    segments = [{"source_text": "Text C New", "translated_text": "Văn bản C Mới", "location": {"slide_id": "slide_1"}}]
    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(diff_ops, segments=segments)

    # Validate deleteObject for img_b comes BEFORE createShape
    del_idx = next(i for i, r in enumerate(batch) if "deleteObject" in r and r["deleteObject"]["objectId"] == "img_b")
    create_idx = next(i for i, r in enumerate(batch) if "createShape" in r)
    assert del_idx < create_idx


def test_sub_diff_and_planner_clear_text_in_existing_shape():
    """Verifies that clearing/deleting text inside an existing shape produces deleteText in batch updates."""
    # Target presentation has a text box with translated text
    tgt_pres = {
        "presentationId": "pres_tgt",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "shape_text_box_1",
                        "size": {"width": {"magnitude": 400.0, "unit": "PT"}, "height": {"magnitude": 50.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 30.0},
                        "shape": {
                            "shapeType": "TEXT_BOX",
                            "text": {"textElements": [{"textRun": {"content": "Nội dung cũ cần xóa\n"}}]}
                        }
                    }
                ]
            }
        ]
    }

    # Source presentation has the same text box, but the text was cleared (empty string / newline)
    src_pres = {
        "presentationId": "pres_src",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [
                    {
                        "objectId": "shape_text_box_1",
                        "size": {"width": {"magnitude": 400.0, "unit": "PT"}, "height": {"magnitude": 50.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 30.0},
                        "shape": {
                            "shapeType": "TEXT_BOX",
                            "text": {"textElements": [{"textRun": {"content": "\n"}}]}
                        }
                    }
                ]
            }
        ]
    }

    src_slides = GoogleSlidesASTParser.parse_presentation(src_pres)
    tgt_slides = GoogleSlidesASTParser.parse_presentation(tgt_pres)

    diff_ops = SlideMyersDiffEngine.diff_slides(src_slides, tgt_slides)
    assert len(diff_ops) == 1
    op = diff_ops[0]
    assert op.op_type == SlideDiffOpType.UPDATE_SLIDE

    clear_diffs = [ed for ed in op.element_diffs if ed.get("type") == "clear_text"]
    assert len(clear_diffs) == 1
    assert clear_diffs[0]["target_element_id"] == "shape_text_box_1"

    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(diff_ops, segments=[])

    # Must generate deleteText with textRange: {"type": "ALL"}
    delete_texts = [r["deleteText"] for r in batch if "deleteText" in r]
    assert len(delete_texts) == 1
    assert delete_texts[0]["objectId"] == "shape_text_box_1"
    assert delete_texts[0]["textRange"]["type"] == "ALL"


def test_sub_diff_and_planner_delete_previous_segment_text():
    """Verifies that if a text from a previous translation run is deleted from source, replaceAllText wipes it from target."""
    diff_ops = [
        SlideDiffOp(
            op_type=SlideDiffOpType.UPDATE_SLIDE,
            source_slide_id="slide_1",
            target_slide_id="slide_1",
            source_slide=SlideASTNode(slide_id="slide_1", slide_index=0, elements=[
                SlideElementASTNode(element_id="shape_title", element_type=SlideElementType.SHAPE, plain_text="タイトル")
            ]),
            target_slide=SlideASTNode(slide_id="slide_1", slide_index=0, elements=[
                SlideElementASTNode(element_id="shape_title", element_type=SlideElementType.SHAPE, plain_text="Tiêu đề")
            ])
        )
    ]

    # Current segments only have title
    current_segments = [
        {"source_text": "タイトル", "translated_text": "Tiêu đề", "location": {"slide_id": "slide_1"}}
    ]

    # Previous segments had an extra text that was deleted in current source
    previous_segments = [
        {"source_text": "タイトル", "translated_text": "Tiêu đề", "location": {"slide_id": "slide_1"}},
        {"source_text": "削除されたパラグラフ", "translated_text": "Đoạn văn đã bị xóa bỏ", "location": {"slide_id": "slide_1"}}
    ]

    batch = SlideReverseIndexBatchPlanner.plan_batch_updates(
        diff_ops=diff_ops,
        segments=current_segments,
        previous_segments=previous_segments
    )

    replace_ops = [r["replaceAllText"] for r in batch if "replaceAllText" in r]
    # Check that "Đoạn văn đã bị xóa bỏ" is replaced with ""
    deleted_replacements = [
        ro for ro in replace_ops
        if ro["containsText"]["text"] == "Đoạn văn đã bị xóa bỏ" and ro["replaceText"] == ""
    ]
    assert len(deleted_replacements) == 1
    assert deleted_replacements[0]["pageObjectIds"] == ["slide_1"]


@pytest.mark.asyncio
async def test_smart_slide_sync_image_ocr_on_slide_3_no_http_crash():
    """Verifies that apply_smart_slide_sync_to_existing_presentation translates images on added slide elements without NameError."""
    src_pres = {
        "presentationId": "pres_src_multi",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [{"objectId": "title_1", "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "S1\n"}}]}}}]
            },
            {
                "objectId": "slide_2",
                "pageElements": []  # Image was deleted on slide 2
            },
            {
                "objectId": "slide_3",
                "pageElements": [
                    {
                        "objectId": "img_new_3",
                        "size": {"width": {"magnitude": 250.0, "unit": "PT"}, "height": {"magnitude": 180.0, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 20.0, "translateY": 40.0},
                        "image": {"contentUrl": "https://example.com/source_diagram_3.png"}
                    }
                ]
            }
        ]
    }

    tgt_pres = {
        "presentationId": "pres_tgt_multi",
        "slides": [
            {
                "objectId": "slide_1",
                "pageElements": [{"objectId": "title_1", "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "S1\n"}}]}}}]
            },
            {
                "objectId": "slide_2",
                "pageElements": [
                    {
                        "objectId": "img_old_2",
                        "image": {"contentUrl": "https://example.com/old_2.png"}
                    }
                ]
            },
            {
                "objectId": "slide_3",
                "pageElements": []  # No image yet on slide 3
            }
        ]
    }

    orig_img_bytes = b"ORIGINAL_BYTES_AT_LEAST_120_CHARACTERS_LONG_FOR_VALIDATION_PURPOSES_ABC123456789_LONG_ENOUGH_BYTES_DATA"
    trans_img_bytes = b"TRANSLATED_BYTES_AT_LEAST_120_CHARACTERS_LONG_FOR_VALIDATION_PURPOSES_ABC123456789_LONG_ENOUGH_BYTES_DATA"

    with patch.object(GoogleSlidesService, "get_presentation", side_effect=[tgt_pres, src_pres]):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.content = orig_img_bytes

            with patch("app.documents.ocr.image_translator.image_translator.process_image", new_callable=AsyncMock, return_value=trans_img_bytes):
                with patch("app.integrations.google.drive.GoogleDriveService.upload_file", new_callable=AsyncMock, return_value={"id": "drive_uploaded_img_3"}) as mock_upload:
                    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                        mock_post.return_value.status_code = 200
                        mock_post.return_value.text = "{}"

                        res = await GoogleSlidesService.apply_smart_slide_sync_to_existing_presentation(
                            access_token="fake_token",
                            target_presentation_id="pres_tgt_multi",
                            source_presentation_id="pres_src_multi",
                            segments=[],
                            translate_images=True,
                            is_mock=False
                        )

                        assert res["status"] == "success"
                        # Verify Drive upload and permission call were made
                        assert mock_upload.called
                        assert mock_post.called

                        # Find the batchUpdate call and verify:
                        # 1. deleteObject for img_old_2 (page 2 image deleted)
                        # 2. createImage for slide 3 has the translated drive image URL!
                        post_calls = mock_post.call_args_list
                        batch_calls = [c for c in post_calls if "batchUpdate" in str(c.args)]
                        assert len(batch_calls) > 0
                        reqs = batch_calls[0].kwargs["json"]["requests"]

                        del_calls = [r for r in reqs if "deleteObject" in r and r["deleteObject"]["objectId"] == "img_old_2"]
                        assert len(del_calls) == 1

                        create_img_calls = [r for r in reqs if "createImage" in r]
                        assert len(create_img_calls) == 1
                        # The created image on slide 3 MUST use the translated drive URL
                        assert "drive_uploaded_img_3" in create_img_calls[0]["createImage"]["url"]


@pytest.mark.asyncio
async def test_fuzzy_structural_matching_when_slide_ids_differ_and_image_added():
    """Verifies that Stage 2b Fuzzy Structural Matching pairs slides with different IDs
    when an image is added, categorizing as UPDATE_SLIDE with insert_element rather than duplicate INSERT_SLIDE."""
    src_pres = {
        "presentationId": "src_diff_ids",
        "slides": [
            {
                "objectId": "g_src_slide_3",
                "pageElements": [
                    {
                        "objectId": "g_title_3",
                        "size": {"width": {"magnitude": 200, "unit": "PT"}, "height": {"magnitude": 40, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 50.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "Sơ đồ kiến trúc\n"}}]}}
                    },
                    {
                        "objectId": "g_desc_3",
                        "size": {"width": {"magnitude": 200, "unit": "PT"}, "height": {"magnitude": 40, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 100.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "Mô tả chi tiết\n"}}]}}
                    },
                    {
                        "objectId": "g_img_new_3",
                        "size": {"width": {"magnitude": 300, "unit": "PT"}, "height": {"magnitude": 200, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 160.0},
                        "image": {"contentUrl": "https://example.com/new_arch.png"}
                    }
                ]
            }
        ]
    }

    tgt_pres = {
        "presentationId": "tgt_diff_ids",
        "slides": [
            {
                "objectId": "slide_ins_abc12345",  # Target slide has generated ID from previous run!
                "pageElements": [
                    {
                        "objectId": "slide_ins_abc12345_sh_0",
                        "size": {"width": {"magnitude": 200, "unit": "PT"}, "height": {"magnitude": 40, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 50.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "アーキテクチャ図\n"}}]}}
                    },
                    {
                        "objectId": "slide_ins_abc12345_sh_1",
                        "size": {"width": {"magnitude": 200, "unit": "PT"}, "height": {"magnitude": 40, "unit": "PT"}},
                        "transform": {"scaleX": 1.0, "scaleY": 1.0, "translateX": 50.0, "translateY": 100.0},
                        "shape": {"shapeType": "TEXT_BOX", "text": {"textElements": [{"textRun": {"content": "詳細説明\n"}}]}}
                    }
                    # Target has NO image yet
                ]
            }
        ]
    }

    src_nodes = GoogleSlidesASTParser.parse_presentation(src_pres)
    tgt_nodes = GoogleSlidesASTParser.parse_presentation(tgt_pres)

    diffs = SlideMyersDiffEngine.diff_slides(src_nodes, tgt_nodes)
    assert len(diffs) == 1
    op = diffs[0]
    # MUST be classified as UPDATE_SLIDE, NOT INSERT_SLIDE!
    assert op.op_type == SlideDiffOpType.UPDATE_SLIDE
    assert op.target_slide_id == "slide_ins_abc12345"

    # Must contain an insert_element for the new image
    insert_els = [ed for ed in op.element_diffs if ed.get("type") == "insert_element"]
    assert len(insert_els) == 1
    assert insert_els[0]["source_element"].element_type == SlideElementType.IMAGE

    # When planned with translated image in image_replacements:
    reqs = SlideReverseIndexBatchPlanner.plan_batch_updates(
        diff_ops=diffs,
        segments=[],
        image_replacements={"g_img_new_3": "https://lh3.googleusercontent.com/d/trans_img_drive_id"}
    )
    create_imgs = [r for r in reqs if "createImage" in r]
    assert len(create_imgs) == 1
    assert create_imgs[0]["createImage"]["url"] == "https://lh3.googleusercontent.com/d/trans_img_drive_id"
    assert create_imgs[0]["createImage"]["elementProperties"]["pageObjectId"] == "slide_ins_abc12345"


@pytest.mark.asyncio
async def test_table_cell_text_mutation_in_plan_batch_updates():
    """Verifies that in-place text mutations in table cells generate deleteText and insertText with cellLocation."""
    src_table = SlideElementASTNode(
        element_id="tbl_1",
        element_type=SlideElementType.TABLE,
        plain_text="Cell 1\nCell 2 Updated\n",
        table_rows=1,
        table_cols=2,
        table_cells=[
            {"row": 0, "col": 0, "text": "Cell 1\n"},
            {"row": 0, "col": 1, "text": "Cell 2 Updated\n"}
        ]
    )
    tgt_table = SlideElementASTNode(
        element_id="tbl_1",
        element_type=SlideElementType.TABLE,
        plain_text="Cell 1\nOld Cell 2\n",
        table_rows=1,
        table_cols=2,
        table_cells=[
            {"row": 0, "col": 0, "text": "Cell 1\n"},
            {"row": 0, "col": 1, "text": "Old Cell 2\n"}
        ]
    )

    diff_op = SlideDiffOp(
        op_type=SlideDiffOpType.UPDATE_SLIDE,
        target_slide_id="slide_table",
        element_diffs=[
            {
                "type": "text_mutation",
                "source_element_id": "tbl_1",
                "target_element_id": "tbl_1",
                "element_type": SlideElementType.TABLE,
                "source_element": src_table,
                "target_element": tgt_table,
                "source_text": "Cell 1\nCell 2 Updated\n",
                "target_text": "Cell 1\nOld Cell 2\n"
            }
        ]
    )

    segments = [
        {"source_text": "Cell 2 Updated", "translated_text": "セルの更新"}
    ]

    reqs = SlideReverseIndexBatchPlanner.plan_batch_updates(
        diff_ops=[diff_op],
        segments=segments
    )

    del_cell = [r for r in reqs if "deleteText" in r and "cellLocation" in r["deleteText"]]
    assert len(del_cell) == 1
    assert del_cell[0]["deleteText"]["cellLocation"] == {"rowIndex": 0, "columnIndex": 1}

    ins_cell = [r for r in reqs if "insertText" in r and "cellLocation" in r["insertText"]]
    assert len(ins_cell) == 1
    assert ins_cell[0]["insertText"]["text"] == "セルの更新"




