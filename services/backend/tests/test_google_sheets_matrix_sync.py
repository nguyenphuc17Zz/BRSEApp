import pytest
from unittest.mock import AsyncMock, patch
from app.integrations.google.sheets_ast_sync import (
    CellType,
    CellBlock,
    RowBlock,
    SheetTab,
    GoogleSheetsGridParser,
    SheetMatrixMyersDiffEngine,
    SheetReverseIndexBatchPlanner,
    SheetDiffOpType,
    SheetDiffOperation,
)
from app.integrations.google.sheets import GoogleSheetsService
from app.documents.models import DocumentSegment


def test_grid_parser_and_formula_immunity():
    sample_sheet_data = {
        "properties": {"title": "Spec Sheet"},
        "sheets": [
            {
                "properties": {"sheetId": 101, "title": "API_Endpoints", "index": 0},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": "Mã chức năng"}},
                                    {"userEnteredValue": {"stringValue": "Tên API"}},
                                    {"userEnteredValue": {"stringValue": "Số lượng tham số"}},
                                    {"userEnteredValue": {"stringValue": "Trạng thái công thức"}},
                                ]
                            },
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": "F01"}},
                                    {"userEnteredValue": {"stringValue": "Đăng nhập người dùng"}},
                                    {"userEnteredValue": {"numberValue": 5}},
                                    {"userEnteredValue": {"formulaValue": "=IF(C2>0, \"OK\", \"EMPTY\")"}},
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    tabs = GoogleSheetsGridParser.parse_spreadsheet(sample_sheet_data)
    assert len(tabs) == 1
    tab = tabs[0]
    assert tab.sheet_id == 101
    assert tab.title == "API_Endpoints"
    assert len(tab.rows) == 2

    # Check header row
    r0 = tab.rows[0]
    assert r0.cells[0].string_value == "Mã chức năng"
    assert r0.cells[0].cell_type == CellType.TEXT
    assert r0.cells[0].is_translatable is True

    # Check data row
    r1 = tab.rows[1]
    assert r1.cells[0].string_value == "F01"
    assert r1.cells[1].string_value == "Đăng nhập người dùng"
    assert r1.cells[1].is_translatable is True

    # Number cell
    assert r1.cells[2].cell_type == CellType.NUMBER
    assert r1.cells[2].is_translatable is False

    # Formula cell: STRICT IMMUNITY
    assert r1.cells[3].cell_type == CellType.FORMULA
    assert r1.cells[3].formula == '=IF(C2>0, "OK", "EMPTY")'
    assert r1.cells[3].is_translatable is False


def test_matrix_myers_diff_row_insertion_and_deletion():
    """Verifies that Myers diff accurately detects deleted rows and newly inserted rows in sheets."""
    # Target Sheet (current Japanese translation with obsolete row)
    target_data = {
        "properties": {"title": "System Architecture"},
        "sheets": [
            {
                "properties": {"sheetId": 0, "title": "Overview"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {"values": [{"userEnteredValue": {"stringValue": "ID"}}, {"userEnteredValue": {"stringValue": "機能名"}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "1"}}, {"userEnteredValue": {"stringValue": "ユーザー認証"}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "2"}}, {"userEnteredValue": {"stringValue": "削除された古い機能"}}]}, # Obsolete
                            {"values": [{"userEnteredValue": {"stringValue": "3"}}, {"userEnteredValue": {"stringValue": "データ分析"}}]},
                        ]
                    }
                ]
            }
        ]
    }

    # Source Sheet (Vietnamese master: item 2 removed, new item 4 inserted between 1 and 3)
    source_data = {
        "properties": {"title": "System Architecture"},
        "sheets": [
            {
                "properties": {"sheetId": 0, "title": "Overview"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {"values": [{"userEnteredValue": {"stringValue": "ID"}}, {"userEnteredValue": {"stringValue": "Tên chức năng"}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "1"}}, {"userEnteredValue": {"stringValue": "Xác thực người dùng (Đã cập nhật)"}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "4"}}, {"userEnteredValue": {"stringValue": "Tích hợp AI mới"}}]}, # Newly inserted
                            {"values": [{"userEnteredValue": {"stringValue": "3"}}, {"userEnteredValue": {"stringValue": "Phân tích dữ liệu"}}]},
                        ]
                    }
                ]
            }
        ]
    }

    src_tabs = GoogleSheetsGridParser.parse_spreadsheet(source_data)
    tgt_tabs = GoogleSheetsGridParser.parse_spreadsheet(target_data)

    current_segs = [
        DocumentSegment(id="s0", job_id="j1", segment_index=0, source_text="Tên chức năng", translated_text="機能名"),
        DocumentSegment(id="s1", job_id="j1", segment_index=1, source_text="Xác thực người dùng (Đã cập nhật)", translated_text="ユーザー認証（更新版）"),
        DocumentSegment(id="s2", job_id="j1", segment_index=2, source_text="Tích hợp AI mới", translated_text="新しいAI統合"),
        DocumentSegment(id="s3", job_id="j1", segment_index=3, source_text="Phân tích dữ liệu", translated_text="データ分析"),
    ]

    engine = SheetMatrixMyersDiffEngine()
    ops = engine.compute_diff(source_tabs=src_tabs, target_tabs=tgt_tabs, current_segments=current_segs)

    # 1. DELETE_ROWS for row 2 (Obsolete row)
    del_op = next((o for o in ops if o.op_type == SheetDiffOpType.DELETE_ROWS), None)
    assert del_op is not None
    assert del_op.start_row_index == 2
    assert del_op.count == 1

    # 2. INSERT_ROWS for newly inserted item 4
    ins_op = next((o for o in ops if o.op_type == SheetDiffOpType.INSERT_ROWS), None)
    assert ins_op is not None
    assert ins_op.count == 1

    # 3. UPDATE_CELLS for updated item 1
    upd_op = next((o for o in ops if o.op_type == SheetDiffOpType.UPDATE_CELLS), None)
    assert upd_op is not None
    updated_cell = next((c for c in upd_op.cell_updates if c["new_value"] == "ユーザー認証（更新版）"), None)
    assert updated_cell is not None


def test_reverse_index_dimension_planner():
    """Verifies that deleteDimension and insertDimension are sorted in descending index order."""
    op_del_high = SheetDiffOperation(
        op_type=SheetDiffOpType.DELETE_ROWS,
        sheet_id=0,
        sheet_title="Sheet1",
        start_row_index=80,
        end_row_index=82,
        count=2
    )
    op_del_low = SheetDiffOperation(
        op_type=SheetDiffOpType.DELETE_ROWS,
        sheet_id=0,
        sheet_title="Sheet1",
        start_row_index=10,
        end_row_index=11,
        count=1
    )
    op_ins_mid = SheetDiffOperation(
        op_type=SheetDiffOpType.INSERT_ROWS,
        sheet_id=0,
        sheet_title="Sheet1",
        start_row_index=50,
        end_row_index=53,
        count=3
    )

    structural_reqs, _ = SheetReverseIndexBatchPlanner.plan_batch_updates([op_del_low, op_del_high, op_ins_mid])

    # Expect: delete at 80 first, then delete at 10, then insert at 50
    assert len(structural_reqs) == 3
    assert structural_reqs[0]["deleteDimension"]["range"]["startIndex"] == 80
    assert structural_reqs[1]["deleteDimension"]["range"]["startIndex"] == 10
    assert structural_reqs[2]["insertDimension"]["range"]["startIndex"] == 50


def test_contiguous_range_aggregation():
    """Verifies that consecutive column cell updates are aggregated into single ValueRanges."""
    raw_updates = [
        {"sheet": "Sheet1", "row": 1, "col": 1, "new_value": "ColB", "old_value": ""},
        {"sheet": "Sheet1", "row": 1, "col": 2, "new_value": "ColC", "old_value": ""},
        {"sheet": "Sheet1", "row": 1, "col": 3, "new_value": "ColD", "old_value": ""},
        {"sheet": "Sheet1", "row": 5, "col": 0, "new_value": "ColA_Row5", "old_value": ""},
    ]

    op = SheetDiffOperation(
        op_type=SheetDiffOpType.UPDATE_CELLS,
        sheet_id=0,
        sheet_title="Sheet1",
        cell_updates=raw_updates
    )

    _, value_ranges = SheetReverseIndexBatchPlanner.plan_batch_updates([op])

    assert len(value_ranges) == 2

    # First range: B2:D2 aggregated
    vr1 = next(v for v in value_ranges if "B2:D2" in v["range"])
    assert vr1["values"] == [["ColB", "ColC", "ColD"]]

    # Second range: A6 isolated
    vr2 = next(v for v in value_ranges if "A6" in v["range"])
    assert vr2["values"] == [["ColA_Row5"]]


@pytest.mark.asyncio
async def test_e2e_apply_smart_matrix_sync_to_existing_sheet():
    """Verifies end-to-end execution of apply_smart_matrix_sync_to_existing_sheet without .xlsx export."""
    target_data_mock = {
        "properties": {"title": "Target Sheet"},
        "sheets": [
            {
                "properties": {"sheetId": 555, "title": "DataTab"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {"values": [{"userEnteredValue": {"stringValue": "Xin chào"}}, {"userEnteredValue": {"formulaValue": "=A1"}}]}]
                    }
                ]
            }
        ]
    }

    seg_c1 = DocumentSegment(
        id="c1",
        job_id="j10",
        segment_index=0,
        location_json='{"sheet": "DataTab", "row": 0, "col": 0}',
        source_text="Xin chào",
        translated_text="こんにちは"
    )

    with patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock, return_value=target_data_mock):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"replies": []}

            await GoogleSheetsService.apply_smart_matrix_sync_to_existing_sheet(
                access_token="test_sheet_token",
                target_spreadsheet_id="target_sheet_999",
                segments=[seg_c1],
                is_mock=False
            )

            assert mock_post.called
            # Check values:batchUpdate was called
            values_call = next(
                (call for call in mock_post.call_args_list if "values:batchUpdate" in str(call)),
                None
            )
            assert values_call is not None
            payload = values_call.kwargs.get("json", {})
            data_list = payload.get("data", [])
            assert len(data_list) == 1
            assert data_list[0]["range"] == "'DataTab'!A1"
            assert data_list[0]["values"] == [["こんにちは"]]


def test_image_formula_parsing():
    """Verifies that GoogleSheetsGridParser extracts image URLs and formula arguments accurately."""
    sample_sheet = {
        "properties": {"title": "Doc with Images"},
        "sheets": [
            {
                "properties": {"sheetId": 1, "title": "Diagrams"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {
                                "values": [
                                    {"userEnteredValue": {"formulaValue": '=IMAGE("https://storage.googleapis.com/test_bucket/arch.png")'}},
                                    {"userEnteredValue": {"formulaValue": '=IMAGE("https://storage.googleapis.com/test_bucket/flowchart.png", 4, 250, 500)'}},
                                    {"userEnteredValue": {"formulaValue": '=SUM(A1:B1)'}} # Standard non-image formula
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    tabs = GoogleSheetsGridParser.parse_spreadsheet(sample_sheet)
    cells = tabs[0].rows[0].cells

    # First cell: simple image
    assert cells[0].is_image_formula is True
    assert cells[0].image_url == "https://storage.googleapis.com/test_bucket/arch.png"
    assert cells[0].image_formula_args == ""
    assert cells[0].cell_type == CellType.FORMULA

    # Second cell: image with mode, width, height arguments
    assert cells[1].is_image_formula is True
    assert cells[1].image_url == "https://storage.googleapis.com/test_bucket/flowchart.png"
    assert cells[1].image_formula_args == "4, 250, 500"

    # Third cell: regular formula
    assert cells[2].is_image_formula is False
    assert cells[2].image_url is None


@pytest.mark.asyncio
async def test_in_cell_image_translation_and_url_replacement():
    """Verifies that in-cell =IMAGE formulas are translated via OCR and updated with new Drive URLs."""
    source_sheet_data = {
        "properties": {"title": "Source Architecture"},
        "sheets": [
            {
                "properties": {"sheetId": 0, "title": "Specs"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": "Sơ đồ kiến trúc"}},
                                    {"userEnteredValue": {"formulaValue": '=IMAGE("https://storage.googleapis.com/test/diagram.png", 1)'}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    target_sheet_data = {
        "properties": {"title": "Target Architecture"},
        "sheets": [
            {
                "properties": {"sheetId": 0, "title": "Specs"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {
                                "values": [
                                    {"userEnteredValue": {"stringValue": "アーキテクチャ図"}},
                                    {"userEnteredValue": {"formulaValue": '=IMAGE("https://storage.googleapis.com/test/old_diagram.png", 1)'}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    fake_orig_bytes = b"ORIGINAL_IMAGE_DATA_PADDING_BYTES_MORE_THAN_100_CHARS_1234567890_ABCDEFGHIJ_KLMNOPQRSTUVWXYZ"
    fake_trans_bytes = b"TRANSLATED_IMAGE_DATA_PADDING_BYTES_MORE_THAN_100_CHARS_1234567890_ABCDEFGHIJ_KLMNOPQRSTUVWXYZ"

    with patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock) as mock_get_sheet:
        mock_get_sheet.side_effect = lambda token, sid, is_mock: target_sheet_data if sid == "target-123" else source_sheet_data

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_http_get:
            mock_http_get.return_value.status_code = 200
            mock_http_get.return_value.content = fake_orig_bytes

            with patch("app.documents.ocr.image_translator.image_translator.process_image", new_callable=AsyncMock, return_value=fake_trans_bytes):
                with patch("app.integrations.google.drive.GoogleDriveService.upload_file", new_callable=AsyncMock, return_value={"id": "drive_uploaded_img_777"}) as mock_upload:
                    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_http_post:
                        mock_http_post.return_value.status_code = 200
                        mock_http_post.return_value.json.return_value = {"replies": []}

                        with patch.object(GoogleSheetsService, "apply_translations_to_copy", new_callable=AsyncMock) as mock_apply_trans:
                            await GoogleSheetsService.apply_smart_matrix_sync_to_existing_sheet(
                                access_token="test_token",
                                target_spreadsheet_id="target-123",
                                source_spreadsheet_id="source-123",
                                segments=[],
                                parent_folder_id="parent_folder_abc",
                                translate_images=True,
                                is_mock=False
                            )

                            assert mock_upload.called
                            assert mock_upload.call_args.kwargs.get("parent_folder_id") == "parent_folder_abc"

                            assert mock_apply_trans.called
                            updates_sent = mock_apply_trans.call_args.kwargs.get("updates") or mock_apply_trans.call_args.args[2]
                            img_update = next((u for u in updates_sent if "drive_uploaded_img_777" in str(u)), None)
                            assert img_update is not None
                            assert img_update["translated_text"] == '=IMAGE("https://lh3.googleusercontent.com/d/drive_uploaded_img_777", 1)'


@pytest.mark.asyncio
async def test_unchanged_image_url_preservation():
    """Verifies that images without translatable text do NOT trigger duplicate uploads."""
    source_sheet_data = {
        "properties": {"title": "Source Architecture"},
        "sheets": [
            {
                "properties": {"sheetId": 0, "title": "Icons"},
                "data": [
                    {
                        "startRow": 0,
                        "rowData": [
                            {
                                "values": [
                                    {"userEnteredValue": {"formulaValue": '=IMAGE("https://example.com/logo.png")'}}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    dummy_bytes = b"ICON_BYTES_IDENTICAL_PADDING_MORE_THAN_100_BYTES_012345678901234567890123456789012345678901234567890123456789"

    with patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock, return_value=source_sheet_data):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_http_get:
            mock_http_get.return_value.status_code = 200
            mock_http_get.return_value.content = dummy_bytes

            # Returns identical bytes (no text detected)
            with patch("app.documents.ocr.image_translator.image_translator.process_image", new_callable=AsyncMock, return_value=dummy_bytes):
                with patch("app.integrations.google.drive.GoogleDriveService.upload_file", new_callable=AsyncMock) as mock_upload:
                    with patch.object(GoogleSheetsService, "apply_translations_to_copy", new_callable=AsyncMock):
                        await GoogleSheetsService.apply_smart_matrix_sync_to_existing_sheet(
                            access_token="test_token",
                            target_spreadsheet_id="target-123",
                            source_spreadsheet_id="source-123",
                            segments=[],
                            translate_images=True,
                            is_mock=False
                        )

                        # Must NOT upload duplicate image when unchanged
                        assert mock_upload.call_count == 0


def test_sheets_multistage_tab_alignment_add_and_delete_sheet():
    """Verifies that Tab Alignment correctly uses sheet_id/index even when tab titles have been translated into Vietnamese,
    and accurately detects ADD_SHEET for new tabs and DELETE_SHEET for obsolete tabs without breaking existing tabs."""
    engine = SheetMatrixMyersDiffEngine()

    # Source Spreadsheet (Japanese, 3 tabs: 2 existing, 1 newly added)
    src_tab_0 = SheetTab(
        sheet_id=0,
        title="概要",
        index=0,
        row_count=10,
        col_count=10,
        rows=[
            RowBlock(sheet_id=0, sheet_title="概要", row_idx=0, cells=[CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="概要", string_value="概要", cell_type=CellType.TEXT)])
        ]
    )
    src_tab_1 = SheetTab(
        sheet_id=101,
        title="システム構成",
        index=1,
        row_count=10,
        col_count=10,
        rows=[
            RowBlock(sheet_id=101, sheet_title="システム構成", row_idx=0, cells=[CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="サーバー", string_value="サーバー", cell_type=CellType.TEXT)])
        ]
    )
    src_tab_2 = SheetTab(
        sheet_id=202,
        title="新機能",
        index=2,
        row_count=10,
        col_count=10,
        rows=[
            RowBlock(sheet_id=202, sheet_title="新機能", row_idx=0, cells=[CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="新機能説明", string_value="新機能説明", cell_type=CellType.TEXT)])
        ]
    )

    # Target Spreadsheet (Vietnamese translation, 2 existing tabs with translated titles, + 1 obsolete tab)
    tgt_tab_0 = SheetTab(
        sheet_id=0,
        title="Tổng quan", # Translated title
        index=0,
        row_count=10,
        col_count=10,
        rows=[
            RowBlock(sheet_id=0, sheet_title="Tổng quan", row_idx=0, cells=[CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="Tổng quan", string_value="Tổng quan", cell_type=CellType.TEXT)])
        ]
    )
    tgt_tab_1 = SheetTab(
        sheet_id=101,
        title="Cấu hình hệ thống", # Translated title
        index=1,
        row_count=10,
        col_count=10,
        rows=[
            RowBlock(sheet_id=101, sheet_title="Cấu hình hệ thống", row_idx=0, cells=[CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="Máy chủ", string_value="Máy chủ", cell_type=CellType.TEXT)])
        ]
    )
    tgt_tab_obsolete = SheetTab(
        sheet_id=999,
        title="Tab cũ cần xóa",
        index=2,
        row_count=10,
        col_count=10,
        rows=[]
    )

    # Current segments mock
    class MockSegment:
        def __init__(self, src, trans):
            self.source_text = src
            self.translated_text = trans
            self.protected_tokens_json = "{}"

    current_segments = [
        MockSegment("新機能", "Tính năng mới"),
        MockSegment("新機能説明", "Mô tả tính năng mới"),
    ]

    ops = engine.compute_diff(
        source_tabs=[src_tab_0, src_tab_1, src_tab_2],
        target_tabs=[tgt_tab_0, tgt_tab_1, tgt_tab_obsolete],
        current_segments=current_segments,
    )

    # Assert ADD_SHEET detected for tab 202
    add_sheet_ops = [op for op in ops if op.op_type == SheetDiffOpType.ADD_SHEET]
    assert len(add_sheet_ops) == 1
    assert add_sheet_ops[0].sheet_id == 202
    assert add_sheet_ops[0].metadata["title"] == "Tính năng mới"
    assert add_sheet_ops[0].metadata["index"] == 2

    # Assert initial cell updates for the new sheet
    new_sheet_cell_updates = [
        op for op in ops 
        if op.op_type == SheetDiffOpType.UPDATE_CELLS and op.sheet_title == "Tính năng mới"
    ]
    assert len(new_sheet_cell_updates) == 1
    assert new_sheet_cell_updates[0].cell_updates[0]["new_value"] == "Mô tả tính năng mới"

    # Assert DELETE_SHEET detected for obsolete tab 999
    delete_sheet_ops = [op for op in ops if op.op_type == SheetDiffOpType.DELETE_SHEET]
    assert len(delete_sheet_ops) == 1
    assert delete_sheet_ops[0].sheet_id == 999
    assert delete_sheet_ops[0].sheet_title == "Tab cũ cần xóa"

    # Plan batch updates and ensure proper payload generation
    structural_reqs, value_ranges = SheetReverseIndexBatchPlanner.plan_batch_updates(ops)
    assert any("addSheet" in req for req in structural_reqs)
    assert any("deleteSheet" in req for req in structural_reqs)
    assert any("Tính năng mới" in vr.get("range", "") for vr in value_ranges)


def test_matrix_diff_cell_clearing_and_addition():
    """Verifies that:
    1. Clearing text in source cell emits new_value == '' to delete text in target cell.
    2. Adding text in previously empty source cell emits new_value == translated_text.
    """
    engine = SheetMatrixMyersDiffEngine()

    src_cells = [
        CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="ID", string_value="ID", cell_type=CellType.TEXT),
        CellBlock(row_idx=0, col_idx=1, cell_ref="B1", raw_value="", string_value="", cell_type=CellType.EMPTY), # DELETED in source!
        CellBlock(row_idx=0, col_idx=2, cell_ref="C1", raw_value="新機能", string_value="新機能", cell_type=CellType.TEXT), # ADDED in source!
    ]
    tgt_cells = [
        CellBlock(row_idx=0, col_idx=0, cell_ref="A1", raw_value="ID", string_value="ID", cell_type=CellType.TEXT),
        CellBlock(row_idx=0, col_idx=1, cell_ref="B1", raw_value="Tên cũ cần xóa", string_value="Tên cũ cần xóa", cell_type=CellType.TEXT), # Should be CLEARED
        CellBlock(row_idx=0, col_idx=2, cell_ref="C1", raw_value="", string_value="", cell_type=CellType.EMPTY), # Should receive "Tính năng mới"
    ]

    src_tab = SheetTab(sheet_id=0, title="Sheet1", index=0, row_count=1, col_count=3, rows=[
        RowBlock(sheet_id=0, sheet_title="Sheet1", row_idx=0, cells=src_cells, anchor_key="id")
    ])
    tgt_tab = SheetTab(sheet_id=0, title="Sheet1", index=0, row_count=1, col_count=3, rows=[
        RowBlock(sheet_id=0, sheet_title="Sheet1", row_idx=0, cells=tgt_cells, anchor_key="id")
    ])

    class MockSegment:
        def __init__(self, src, trans):
            self.source_text = src
            self.translated_text = trans
            self.protected_tokens_json = "{}"

    current_segments = [
        MockSegment("新機能", "Tính năng mới"),
    ]

    ops = engine.compute_diff(
        source_tabs=[src_tab],
        target_tabs=[tgt_tab],
        current_segments=current_segments
    )

    update_ops = [op for op in ops if op.op_type == SheetDiffOpType.UPDATE_CELLS]
    assert len(update_ops) >= 1

    all_cell_updates = []
    for op in update_ops:
        all_cell_updates.extend(op.cell_updates)

    # 1. Verify cell B1 (col 1) is cleared (new_value == "")
    cleared_cell = next((c for c in all_cell_updates if c["col"] == 1), None)
    assert cleared_cell is not None, "Expected cell B1 to be cleared"
    assert cleared_cell["new_value"] == "", f"Expected empty string for cleared cell, got: {cleared_cell['new_value']}"

    # 2. Verify cell C1 (col 2) receives "Tính năng mới"
    added_cell = next((c for c in all_cell_updates if c["col"] == 2), None)
    assert added_cell is not None, "Expected cell C1 to receive translated text"
    assert added_cell["new_value"] == "Tính năng mới"



