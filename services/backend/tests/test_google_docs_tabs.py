import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.integrations.google.docs import GoogleDocsService
from app.integrations.google.drive import GoogleDriveService

SAMPLE_MULTI_TAB_DOC = {
    "title": "Tài liệu Yêu cầu Kỹ thuật (SRS)",
    "revisionId": "rev-123",
    "tabs": [
        {
            "tabProperties": {
                "tabId": "t.0",
                "title": "Tổng quan",
                "index": 0
            },
            "documentTab": {
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                "elements": [{"textRun": {"content": "1. Giới thiệu dự án\n"}}]
                            }
                        },
                        {
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                "elements": [{"textRun": {"content": "Hệ thống hỗ trợ dịch thuật tự động cho BRSE.\n"}}]
                            }
                        }
                    ]
                }
            }
        },
        {
            "tabProperties": {
                "tabId": "t.1",
                "title": "Bảng thiết kế DB",
                "index": 1
            },
            "documentTab": {
                "body": {
                    "content": [
                        {
                            "paragraph": {
                                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                "elements": [{"textRun": {"content": "2. Cấu trúc CSDL\n"}}]
                            }
                        },
                        {
                            "table": {
                                "tableRows": [
                                    {
                                        "tableCells": [
                                            {
                                                "content": [
                                                    {
                                                        "paragraph": {
                                                            "elements": [{"textRun": {"content": "Tên trường"}}]
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "content": [
                                                    {
                                                        "paragraph": {
                                                            "elements": [{"textRun": {"content": "Mô tả ý nghĩa"}}]
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "tableCells": [
                                            {
                                                "content": [
                                                    {
                                                        "paragraph": {
                                                            "elements": [{"textRun": {"content": "user_id"}}]
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "content": [
                                                    {
                                                        "paragraph": {
                                                            "elements": [{"textRun": {"content": "Mã định danh người dùng"}}]
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    ]
                }
            },
            "childTabs": [
                {
                    "tabProperties": {
                        "tabId": "t.1.1",
                        "title": "Phụ lục bảo mật",
                        "index": 2
                    },
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "paragraph": {
                                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                                        "elements": [{"textRun": {"content": "Quy tắc mã hóa dữ liệu người dùng.\n"}}]
                                    }
                                }
                            ]
                        }
                    }
                }
            ]
        }
    ]
}

SAMPLE_LEGACY_DOC = {
    "title": "Legacy Single Tab Doc",
    "revisionId": "rev-legacy",
    "body": {
        "content": [
            {
                "paragraph": {
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "elements": [{"textRun": {"content": "Văn bản tài liệu đơn không chia thẻ.\n"}}]
                }
            }
        ]
    }
}


def test_parse_segments_multi_tab_all():
    """Test parsing all tabs including nested child tabs and tables."""
    segments, meta = GoogleDocsService.parse_segments(SAMPLE_MULTI_TAB_DOC)
    
    assert meta["total_segments"] > 0
    assert len(meta["tabs"]) == 3  # t.0, t.1, t.1.1
    assert len(meta["processed_tabs"]) == 3
    
    # Check that segments from different tabs exist
    tab_ids = {s.location.get("tab_id") for s in segments}
    assert "t.0" in tab_ids
    assert "t.1" in tab_ids
    assert "t.1.1" in tab_ids
    
    # Check table parsing
    table_segments = [s for s in segments if s.location.get("tab_id") == "t.1"]
    texts = [s.source_text for s in table_segments]
    assert any("Tên trường" in t for t in texts)
    assert any("Mô tả ý nghĩa" in t for t in texts)
    assert any("user_id" in t for t in texts)
    assert any("Mã định danh người dùng" in t for t in texts)


def test_parse_segments_filter_selected_tabs():
    """Test parsing only the selected tab."""
    segments, meta = GoogleDocsService.parse_segments(SAMPLE_MULTI_TAB_DOC, selected_tabs=["t.0"])
    
    assert len(meta["processed_tabs"]) == 1
    assert meta["processed_tabs"][0]["id"] == "t.0"
    
    tab_ids = {s.location.get("tab_id") for s in segments}
    assert tab_ids == {"t.0"}
    assert len(segments) == 2  # 2 paragraphs in t.0


def test_parse_segments_legacy_doc():
    """Test backward compatibility with single-body legacy docs."""
    segments, meta = GoogleDocsService.parse_segments(SAMPLE_LEGACY_DOC)
    
    assert meta["total_segments"] == 1
    assert segments[0].source_text == "Văn bản tài liệu đơn không chia thẻ."
    assert segments[0].location.get("tab_id") == "t.0"


@pytest.mark.asyncio
async def test_get_metadata():
    """Test get_metadata returns tab information."""
    with patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = SAMPLE_MULTI_TAB_DOC
        meta = await GoogleDocsService.get_metadata("mock_token", "doc-123")
        
        assert meta["format"] == "gdoc"
        assert len(meta["tabs"]) == 3
        assert "Tổng quan" in meta["tab_names"]
        assert "Bảng thiết kế DB" in meta["tab_names"]
        assert "Phụ lục bảo mật" in meta["tab_names"]


@pytest.mark.asyncio
async def test_apply_translations_with_tabs_criteria():
    """Test that tabsCriteria is included when selected_tabs is provided."""
    translations = [
        {"source_text": "Giới thiệu", "translated_text": "Introduction"}
    ]
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        
        await GoogleDocsService.apply_translations_to_copy(
            access_token="test_token",
            copy_document_id="copy_123",
            translations=translations,
            selected_tabs=["t.0"]
        )
        
        assert mock_post.called
        call_args = mock_post.call_args[1]
        payload = call_args["json"]
        req = payload["requests"][0]["replaceAllText"]
        assert req["tabsCriteria"] == {"tabIds": ["t.0"]}
        assert req["replaceText"] == "Introduction"


@pytest.mark.asyncio
async def test_apply_translations_without_tabs_criteria():
    """Test that tabsCriteria is omitted when selected_tabs is None (translates all tabs)."""
    translations = [
        {"source_text": "Giới thiệu", "translated_text": "Introduction"}
    ]
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        
        await GoogleDocsService.apply_translations_to_copy(
            access_token="test_token",
            copy_document_id="copy_123",
            translations=translations,
            selected_tabs=None
        )
        
        assert mock_post.called
        call_args = mock_post.call_args[1]
        payload = call_args["json"]
        req = payload["requests"][0]["replaceAllText"]
        assert "tabsCriteria" not in req
        assert req["replaceText"] == "Introduction"


@pytest.mark.asyncio
async def test_sync_existing_file_content_skips_docx_for_gdoc():
    """Test that GoogleDriveService.sync_existing_file_content preserves native multi-tab structure for Google Docs by skipping DOCX export."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        res = await GoogleDriveService.sync_existing_file_content(
            access_token="test_token",
            source_file_id="source_doc_123",
            target_file_id="target_doc_456",
            file_type="gdoc",
            is_mock=False
        )
        assert res is True
        # Verify that Drive API export was NEVER called for gdoc
        assert not mock_get.called


def test_apply_smart_title_fallback():
    """Test that apply_smart_title_fallback accurately translates typical Vietnamese IT tab titles to Japanese."""
    from app.integrations.google.docs import apply_smart_title_fallback
    assert apply_smart_title_fallback("01 - Tổng Quan & Yêu Cầu", "vi", "ja") == "01 - 概要・要件"
    assert apply_smart_title_fallback("02 - Kiến Trúc & Sơ Đồ", "vi", "ja") == "02 - アーキテクチャ・図"
    assert apply_smart_title_fallback("Thiết Kế CSDL", "vi", "ja") == "DB設計"


@pytest.mark.asyncio
async def test_translate_and_update_tab_titles_smart_fallback_on_ai_failure():
    """Test that when AI provider fails (e.g. 429 rate limit), tab titles are still translated to Japanese via smart fallback."""
    mock_provider = AsyncMock()
    mock_provider.generate.side_effect = RuntimeError("Groq 429 rate limit exceeded")

    sample_doc = {
        "tabs": [
            {"tabProperties": {"tabId": "t.0", "title": "01 - Tổng Quan & Yêu Cầu"}},
            {"tabProperties": {"tabId": "t.1", "title": "02 - Kiến Trúc & Sơ Đồ"}}
        ]
    }

    with patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=sample_doc), \
         patch("app.providers.registry.provider_registry.get_provider", return_value=None), \
         patch.object(GoogleDocsService, "update_tab_titles", new_callable=AsyncMock) as mock_update:

        await GoogleDocsService.translate_and_update_tab_titles(
            access_token="test_token",
            copy_document_id="doc_123",
            source_document_id=None,
            source_lang="vi",
            target_lang="ja",
            provider=mock_provider,
            model="qwen/qwen3.6-27b",
            is_mock=False
        )

        assert mock_update.called
        updates = mock_update.call_args[0][2]
        assert len(updates) == 2
        assert updates[0]["title"] == "01 - 概要・要件"
        assert updates[1]["title"] == "02 - アーキテクチャ・図"


@pytest.mark.asyncio
async def test_sync_document_tabs_add_tab_and_delete_tab():
    """Test Two-Phase Tab Synchronization:
    - Detects newly added source tab 't.2' and calls addDocumentTab with translated title.
    - Captures new_target_tab_id from API response and populates tab_map.
    - Detects obsolete target tab 't.old' and calls deleteTab.
    """
    source_tabs = [
        {"tabProperties": {"tabId": "t.0", "title": "01 - Tổng Quan", "index": 0}},
        {"tabProperties": {"tabId": "t.1", "title": "02 - Thiết Kế CSDL", "index": 1}},
        {"tabProperties": {"tabId": "t.2", "title": "03 - Phụ Lục Kỹ Thuật", "index": 2, "iconEmoji": "🔒"}},
    ]
    target_tabs = [
        {"tabProperties": {"tabId": "t.0", "title": "01 - 概要", "index": 0}},
        {"tabProperties": {"tabId": "t.1", "title": "02 - DB設計", "index": 1}},
        {"tabProperties": {"tabId": "t.old", "title": "Thẻ Cũ Đã Xóa", "index": 2}},
    ]

    add_resp_data = {
        "replies": [
            {
                "addDocumentTab": {
                    "tabProperties": {
                        "tabId": "t.new_target_tab_123",
                        "title": "03 - 付録・技術",
                        "index": 2,
                        "iconEmoji": "🔒"
                    }
                }
            }
        ]
    }

    call_records = []

    async def mock_post(url, headers=None, json=None):
        call_records.append({"url": url, "json": json})
        resp = MagicMock()
        resp.status_code = 200
        if json and any("addDocumentTab" in req for req in json.get("requests", [])):
            resp.json.return_value = add_resp_data
        else:
            resp.json.return_value = {"replies": [{}]}
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        tab_map = await GoogleDocsService.sync_document_tabs(
            access_token="test_token",
            target_document_id="doc_target_456",
            source_tabs=source_tabs,
            target_tabs=target_tabs,
            source_lang="vi",
            target_lang="ja",
            is_mock=False
        )

        assert tab_map["t.0"] == "t.0"
        assert tab_map["t.1"] == "t.1"
        assert tab_map["t.2"] == "t.new_target_tab_123"

        # Verify addDocumentTab was called for t.2
        add_calls = [c for c in call_records if any("addDocumentTab" in req for req in c["json"].get("requests", []))]
        assert len(add_calls) == 1
        add_req = add_calls[0]["json"]["requests"][0]["addDocumentTab"]
        assert add_req["tabProperties"]["iconEmoji"] == "🔒"
        assert "03" in add_req["tabProperties"]["title"]

        # Verify deleteTab was called for t.old
        del_calls = [c for c in call_records if any("deleteTab" in req for req in c["json"].get("requests", []))]
        assert len(del_calls) == 1
        del_req = del_calls[0]["json"]["requests"][0]["deleteTab"]
        assert del_req["tabId"] == "t.old"


def test_batch_planner_new_tab_end_of_segment_order():
    """Test that multiple blocks in a newly created tab (marked with end_of_segment: True)
    generate endOfSegmentLocation requests and are preserved in natural ascending chronological order.
    """
    from app.integrations.google.ast_sync import (
        ASTBlock,
        ASTBlockType,
        DiffOperation,
        DiffOpType,
        ReverseIndexBatchPlanner,
    )

    b0 = ASTBlock(
        tab_id="t.new",
        block_index=0,
        start_index=1,
        end_index=20,
        block_type=ASTBlockType.HEADING_1,
        raw_text="Tiêu đề chương mới",
        cleaned_text="Tiêu đề chương mới"
    )
    b1 = ASTBlock(
        tab_id="t.new",
        block_index=1,
        start_index=21,
        end_index=80,
        block_type=ASTBlockType.PARAGRAPH,
        raw_text="Đoạn văn nội dung 1",
        cleaned_text="Đoạn văn nội dung 1"
    )
    b2 = ASTBlock(
        tab_id="t.new",
        block_index=2,
        start_index=81,
        end_index=140,
        block_type=ASTBlockType.PARAGRAPH,
        raw_text="Đoạn văn nội dung 2",
        cleaned_text="Đoạn văn nội dung 2"
    )

    op0 = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.new",
        source_block=b0,
        new_text="新章のタイトル",
        target_anchor_index=1,
        metadata={"end_of_segment": True}
    )
    op1 = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.new",
        source_block=b1,
        new_text="段落コンテンツ 1",
        target_anchor_index=1,
        metadata={"end_of_segment": True}
    )
    op2 = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.new",
        source_block=b2,
        new_text="段落コンテンツ 2",
        target_anchor_index=1,
        metadata={"end_of_segment": True}
    )

    # Also add a standard index-based mutation on an existing tab to verify priority
    op_legacy = DiffOperation(
        op_type=DiffOpType.INSERT_BLOCK,
        tab_id="t.0",
        source_block=None,
        new_text="Legacy insert at 150",
        target_anchor_index=150,
        metadata={}
    )

    replace_reqs, index_reqs = ReverseIndexBatchPlanner.plan_batch_updates([op0, op1, op2, op_legacy])

    # 1. Existing index mutation (150) must execute first
    assert index_reqs[0]["insertText"]["location"]["index"] == 150

    # 2. EOS insertions must follow in exact chronological forward order (op0, op1, op2)
    eos_reqs = [r for r in index_reqs if "endOfSegmentLocation" in r.get("insertText", {})]
    assert len(eos_reqs) == 3
    assert eos_reqs[0]["insertText"]["endOfSegmentLocation"]["tabId"] == "t.new"
    assert "新章のタイトル" in eos_reqs[0]["insertText"]["text"]
    assert "段落コンテンツ 1" in eos_reqs[1]["insertText"]["text"]
    assert "段落コンテンツ 2" in eos_reqs[2]["insertText"]["text"]


@pytest.mark.asyncio
async def test_apply_smart_delta_sync_to_existing_doc_with_tab_sync():
    """Test full integration of apply_smart_delta_sync_to_existing_doc:
    - Calls sync_document_tabs during Phase 1.
    - Remaps ASTBlock tab_ids to new target tab_ids.
    - Dispatches planned requests to Google Docs batchUpdate.
    """
    source_doc = {
        "title": "Source Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 0"},
                "documentTab": {
                    "body": {
                        "content": [
                            {"startIndex": 1, "endIndex": 20, "paragraph": {"elements": [{"textRun": {"content": "Source Text Tab 0\n"}}]}}
                        ]
                    }
                }
            },
            {
                "tabProperties": {"tabId": "t.new_src", "title": "Tab Mới"},
                "documentTab": {
                    "body": {
                        "content": [
                            {"startIndex": 1, "endIndex": 25, "paragraph": {"elements": [{"textRun": {"content": "Nội dung tab mới\n"}}]}}
                        ]
                    }
                }
            }
        ]
    }

    target_doc_initial = {
        "title": "Target Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 0"},
                "documentTab": {
                    "body": {
                        "content": [
                            {"startIndex": 1, "endIndex": 20, "paragraph": {"elements": [{"textRun": {"content": "Target Text Tab 0\n"}}]}}
                        ]
                    }
                }
            }
        ]
    }

    target_doc_refreshed = {
        "title": "Target Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 0"},
                "documentTab": {
                    "body": {
                        "content": [
                            {"startIndex": 1, "endIndex": 20, "paragraph": {"elements": [{"textRun": {"content": "Target Text Tab 0\n"}}]}}
                        ]
                    }
                }
            },
            {
                "tabProperties": {"tabId": "t.target_created_999", "title": "新タブ"},
                "documentTab": {
                    "body": {
                        "content": []
                    }
                }
            }
        ]
    }

    batch_update_calls = []

    async def mock_batch_post(url, headers=None, json=None):
        batch_update_calls.append(json)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"replies": []}
        return resp

    with patch.object(GoogleDocsService, "get_document_content") as mock_get_doc, \
         patch.object(GoogleDocsService, "sync_document_tabs") as mock_sync_tabs, \
         patch("httpx.AsyncClient.post", side_effect=mock_batch_post):

        mock_get_doc.side_effect = [target_doc_initial, source_doc, target_doc_refreshed]
        mock_sync_tabs.return_value = {"t.0": "t.0", "t.new_src": "t.target_created_999"}

        await GoogleDocsService.apply_smart_delta_sync_to_existing_doc(
            access_token="mock_token",
            target_document_id="tgt_doc_id",
            segments=[],
            previous_segments=[],
            source_document_id="src_doc_id",
            is_mock=False
        )

        assert mock_sync_tabs.called
        assert len(batch_update_calls) > 0
        all_reqs = [r for call in batch_update_calls for r in call.get("requests", [])]
        assert any(
            r.get("insertText", {}).get("endOfSegmentLocation", {}).get("tabId") == "t.target_created_999"
            or r.get("insertText", {}).get("location", {}).get("tabId") == "t.target_created_999"
            for r in all_reqs
        )



