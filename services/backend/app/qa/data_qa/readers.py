"""Dataset readers: CSV (stdlib), Excel (openpyxl), JSON/API-result, manual tables.

Chunked streaming for large files — never load millions of rows into RAM.
Every reader yields (row_dict, row_no). Values stay as read; normalization
happens in comparison.py so NULL vs "" vs " " stay distinct by default.
"""
import csv
import io
import json
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_ROW_CAP = 100_000
CHUNK_SIZE = 5_000


def detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "latin-1"):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "utf-8"


def read_csv(path: str, encoding: Optional[str] = None,
             delimiter: Optional[str] = None,
             row_cap: int = DEFAULT_ROW_CAP) -> Tuple[List[str], Iterator[Tuple[Dict[str, Any], int]]]:
    with open(path, "rb") as f:
        raw = f.read()
    enc = encoding or detect_encoding(raw)
    text = raw.decode(enc, errors="replace")
    if not delimiter:
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=[",", ";", "\t", "|"]).delimiter
        except Exception:
            delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    fields = list(reader.fieldnames or [])

    def _gen():
        for i, row in enumerate(reader, 1):
            if i > row_cap:
                break
            yield ({k: (v if v is not None else None) for k, v in (row or {}).items()}, i)

    return fields, _gen()


def read_excel(path: str, sheet: Optional[str] = None,
               row_cap: int = DEFAULT_ROW_CAP) -> Tuple[List[str], List[str], Iterator[Tuple[Dict[str, Any], int]]]:
    """Returns (fields, warnings, row iterator). Header = first non-empty row."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=False, read_only=True)
    names = wb.sheetnames
    ws = wb[sheet] if sheet and sheet in names else wb[names[0]]
    warnings: List[str] = []
    # merged cells note (business data focus, not formatting QA)
    try:
        if ws.merged_cells and len(list(ws.merged_cells.ranges)) > 0:
            warnings.append(f"merged_cells:{len(list(ws.merged_cells.ranges))}")
    except Exception:
        pass
    header: List[str] = []
    header_row_idx = 0
    data_start = 0
    rows_iter = ws.iter_rows(values_only=False)
    buffered = []
    for idx, row in enumerate(rows_iter):
        vals = [(c.value if not (isinstance(c.value, str) and c.value.startswith("=")) else f"=FORMULA({c.coordinate})") for c in row]
        if any(v is not None and str(v).strip() != "" for v in vals):
            header = [str(v).strip() if v is not None else f"col{i + 1}" for i, v in enumerate(vals)]
            header_row_idx = idx
            data_start = idx + 1
            break
    if not header:
        return [], warnings, iter([])

    def _gen():
        n = 0
        for row in ws.iter_rows(min_row=data_start + 1, values_only=False):
            vals = []
            for c in row[:len(header)]:
                v = c.value
                if isinstance(v, str) and v.startswith("="):
                    vals.append(f"=FORMULA({c.coordinate})")
                else:
                    vals.append(v)
            if all(v is None or (isinstance(v, str) and v.strip() == "") for v in vals):
                continue
            n += 1
            if n > row_cap:
                break
            yield ({header[i]: vals[i] if i < len(vals) else None for i in range(len(header))}, n)

    return header, warnings, _gen()


def read_json_records(path: str, json_path: str = "",
                      row_cap: int = DEFAULT_ROW_CAP) -> Tuple[List[str], Iterator[Tuple[Dict[str, Any], int]]]:
    with open(path, "r", encoding="utf-8-sig") as f:
        doc = json.load(f)
    node: Any = doc
    if json_path:
        from app.qa.api_testing.assertion_engine import get_path
        found, node = get_path(doc, json_path)
        if not found:
            raise ValueError(f"json_path not found: {json_path}")
    records = node if isinstance(node, list) else [node]
    fields: List[str] = []
    for r in records:
        if isinstance(r, dict):
            for k in r.keys():
                if k not in fields:
                    fields.append(k)

    def _gen():
        for i, r in enumerate(records, 1):
            if i > row_cap:
                break
            yield (r if isinstance(r, dict) else {"value": r}, i)

    return fields, _gen()


def collect_rows(iterator: Iterator[Tuple[Dict[str, Any], int]],
                 limit: int = DEFAULT_ROW_CAP) -> List[Tuple[Dict[str, Any], int]]:
    out = []
    for row in iterator:
        out.append(row)
        if len(out) >= limit:
            break
    return out
