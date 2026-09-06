import pytest
from unittest.mock import patch, AsyncMock
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


