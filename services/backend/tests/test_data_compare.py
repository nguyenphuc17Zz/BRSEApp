"""Phase 6 pure-engine tests: readers, comparison, transforms, rules, guarded SQL."""
import pytest
from app.qa.data_qa import readers, comparison as C, transforms as T
from app.qa.data_qa import rules_engine as RE


def _rows(pairs):
    return [({"order_no": k, **v}, i + 1) for i, (k, v) in enumerate(pairs)]


def test_count_key_field_mismatch():
    src = _rows([("A1", {"status": "OPEN"}), ("A2", {"status": "COMPLETE"})])
    dst = _rows([("A1", {"status": "OPEN"})])
    si, _ = C.index_by_key(src, ["order_no"])
    di, _ = C.index_by_key(dst, ["order_no"])
    assert C.compare_counts(2, 1) == {"source": 2, "dest": 1, "diff": -1, "match": False}
    missing, extra = C.find_missing_extra(si, di)
    assert missing == ["A1"] or "A2" in missing
    assert extra == []
    maps = [{"source_field": "status", "dest_field": "status"}]
    mm = C.compare_fields(si["A1"][0], di["A1"][0], maps)
    assert mm == []


def test_field_mismatch_and_ignore():
    src = ({"status": "OPEN", "updated_at": "2026/01/01"}, 1)
    dst = ({"status": "COMPLETE", "updated_at": "2026/09/27"}, 1)
    maps = [{"source_field": "status", "dest_field": "status"},
            {"source_field": "updated_at", "dest_field": "updated_at", "ignored": True}]
    mm = C.compare_fields(src[0], dst[0], maps)
    assert len(mm) == 1 and mm[0]["field"] == "status"
    assert mm[0]["expected"] == "OPEN" and mm[0]["actual"] == "COMPLETE"


def test_null_empty_blank_zero_distinct():
    assert not T.values_equal(None, "")
    assert not T.values_equal("", " ")
    assert not T.values_equal(" ", "  ")
    assert not T.values_equal(0, "")
    assert not T.values_equal(None, 0)
    assert T.values_equal("100", "100")
    assert T.describe_value(None) == "NULL"
    assert T.describe_value("") == '""(empty)'
    assert T.describe_value(" ") == '" "(blank)'


def test_transforms():
    assert T.apply_transform("20260927", {"op": "date_format", "from": "%Y%m%d", "to": "%Y/%m/%d"}) == "2026/09/27"
    assert T.apply_transform("  a ", {"op": "trim"}) == "a"
    assert T.apply_transform("ABC", {"op": "lower"}) == "abc"
    assert T.apply_transform("1", {"op": "bool_map"}) is True
    assert T.apply_transform("OLD", {"op": "code_map", "mapping": {"OLD": "NEW"}}) == "NEW"
    assert T.apply_transform("a,b", {"op": "split", "sep": ",", "index": 1}) == "b"
    assert T.apply_transform("ＡＢＣ", {"op": "half_width"}) == "ABC"


def test_duplicates_and_possible():
    rows = [({"order_no": "A1", "name": "Taro", "phone": "090"}, 1),
            ({"order_no": "A1", "name": "Taro", "phone": "090"}, 2),
            ({"order_no": "A2", "name": "Taro", "phone": "090"}, 3)]
    index, dups = C.index_by_key(rows, ["order_no"])
    confirmed = C.detect_duplicates(index, dups)
    assert len(confirmed) == 1 and confirmed[0]["key"] == "A1"
    for row, _ in rows:
        row["__biz_key__"] = row["order_no"]
    poss = C.detect_possible_duplicates(rows, ["name", "phone"])
    assert any(p["kind"] == "possible_duplicate" for p in poss)


def test_encoding_and_date_numeric():
    assert C.check_encoding("文字化けÃ© test", "f") is not None
    assert C.check_encoding("正常なテキスト", "f") is None
    assert C.check_encoding("ｱｲｳ", "f") is not None  # half-width katakana flagged
    assert C.check_encoding("clean ascii", "f") is None
    assert C.check_date("2026/09/27", "d") is None
    assert C.check_date("2026-13-99", "d") is not None
    assert C.check_date(None, "d") is None
    assert C.check_date(None, "d", allow_null=False) is not None
    assert C.check_numeric("100.00", "n", {"precision": 2}) is None
    assert C.check_numeric("100.0", "n", {"precision": 2}) is not None
    assert C.check_numeric("abc", "n") is not None
    assert C.check_numeric("-5", "n", {"min": 0}) is not None


def test_rule_eval_row_level():
    assert RE.eval_rule_on_row("required", {"field": "email"}, {"email": ""}) is not None
    assert RE.eval_rule_on_row("required", {"field": "email"}, {"email": "a@b"}) is None
    assert RE.eval_rule_on_row("cross_field",
                               {"if": {"field": "status", "condition": "eq", "value": "COMPLETE"},
                                "then": {"field": "completed_at", "condition": "not_empty"}},
                               {"status": "COMPLETE", "completed_at": None}) is not None
    assert RE.eval_rule_on_row("cross_field",
                               {"if": {"field": "status", "condition": "eq", "value": "COMPLETE"},
                                "then": {"field": "completed_at", "condition": "not_empty"}},
                               {"status": "OPEN", "completed_at": None}) is None
    assert RE.eval_rule_on_row("consistency",
                               {"field_a": "created_at", "field_b": "updated_at", "relation": "lte"},
                               {"created_at": "2026/09/28", "updated_at": "2026/09/27"}) is not None
    assert RE.eval_rule_on_row("consistency",
                               {"field_a": "created_at", "field_b": "updated_at", "relation": "lte"},
                               {"created_at": "2026/09/27", "updated_at": "2026/09/27"}) is None


def test_unique_and_calculation():
    rows = [({"email": "a@x"}, 1), ({"email": "a@x"}, 2), ({"email": "b@x"}, 3)]
    assert len(RE.eval_unique(rows, ["email"])) == 1
    headers = [{"order_no": "O1", "total": "300"}, {"order_no": "O2", "total": "100"}]
    details = [{"order_no": "O1", "amount": "100"}, {"order_no": "O1", "amount": "200"},
               {"order_no": "O2", "amount": "99.99"}]
    out = RE.eval_calculation(headers, details, {
        "header_key": "order_no", "header_field": "total",
        "detail_key": "order_no", "detail_field": "amount"})
    assert len(out) == 1 and out[0]["key"] == "O2"


def test_guarded_sql_allows_select_blocks_destructive():
    rows = [{"order_no": "O1", "status": "COMPLETE", "completed_at": None},
            {"order_no": "O2", "status": "OPEN", "completed_at": None}]
    bad = RE.run_guarded_sql(
        rows, "SELECT * FROM data WHERE status = 'COMPLETE' AND completed_at IS NULL")
    assert len(bad) == 1 and bad[0]["order_no"] == "O1"
    for evil in ["DELETE FROM data", "DROP TABLE data", "UPDATE data SET x=1",
                 "INSERT INTO data VALUES (1)", "SELECT * FROM data; DELETE FROM data",
                 "PRAGMA table_info(data)", "ALTER TABLE data ADD COLUMN x"]:
        with pytest.raises(ValueError):
            RE.run_guarded_sql(rows, evil)


def test_csv_reader_and_encoding(tmp_path):
    p = tmp_path / "orders.csv"
    p.write_bytes("order_no,status\nA1,OPEN\nA2,完了\n".encode("utf-8-sig"))
    fields, it = readers.read_csv(str(p))
    assert fields == ["order_no", "status"]
    rows = list(it)
    assert len(rows) == 2 and rows[1][0]["status"] == "完了"
    assert readers.detect_encoding("あいう".encode("utf-8")) in ("utf-8-sig", "utf-8")


def test_excel_reader_values_and_formula(tmp_path):
    from openpyxl import Workbook
    p = str(tmp_path / "t.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.append(["order_no", "total"])
    ws.append(["O1", 100])
    ws.append(["O2", "=SUM(A1:A2)"])
    wb.save(p)
    fields, warnings, it = readers.read_excel(p)
    assert fields == ["order_no", "total"]
    rows = list(it)
    assert len(rows) == 2
    assert rows[1][0]["total"].startswith("=FORMULA(")


def test_severity_reasons():
    sev, reason = C.severity_for("missing", "order_no", "Order Migration")
    assert sev == "HIGH" and reason
    sev2, _ = C.severity_for("mismatch", "display_name", "")
    assert sev2 in ("LOW", "MEDIUM")
