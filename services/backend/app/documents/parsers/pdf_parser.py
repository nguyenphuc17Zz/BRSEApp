from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import pymupdf as fitz # PyMuPDF
from app.documents.parsers.base import DocumentParser
from app.documents.segmenter import ParsedSegment, TokenProtector

class PdfParser(DocumentParser):
    """Parses PDF documents with native text extraction, bounding boxes, and scan detection."""

    def parse(self, file_path: Path, options: Optional[Dict[str, Any]] = None) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        doc = fitz.open(str(file_path))
        segments: List[ParsedSegment] = []
        segment_index = 0
        scanned_pages = []

        for page_idx, page in enumerate(doc):
            # Extract text blocks: (x0, y0, x1, y1, text, block_no, block_type)
            blocks = page.get_text("blocks")
            page_text_len = 0

            # Pre-parse dict for rich typography metadata
            try:
                page_dict = page.get_text("dict")
                dict_blocks_by_number = {
                    d_b.get("number", idx): d_b
                    for idx, d_b in enumerate(page_dict.get("blocks", []))
                    if d_b.get("type") == 0
                }
            except Exception:
                dict_blocks_by_number = {}

            for b in blocks:
                # b[4] is text, b[6] is block_type (0 for text, 1 for image)
                if len(b) > 6 and b[6] == 0:
                    raw_text = b[4].strip()
                    if not raw_text:
                        continue

                    page_text_len += len(raw_text)
                    protected_text, token_map = TokenProtector.protect_tokens(raw_text)
                    b_no = b[5]
                    b_bbox = [round(coord, 2) for coord in b[:4]]

                    # Extract rich typography from page dict
                    block_dict = dict_blocks_by_number.get(b_no)
                    font_size = None
                    font_color = [0.0, 0.0, 0.0]
                    is_bold = False
                    is_italic = False
                    align = 0  # 0=left, 1=center, 2=right

                    if block_dict and "lines" in block_dict:
                        sizes = []
                        colors = []
                        line_x_starts = []
                        line_x_ends = []
                        for line in block_dict["lines"]:
                            l_bbox = line.get("bbox", [])
                            if len(l_bbox) == 4:
                                line_x_starts.append(l_bbox[0])
                                line_x_ends.append(l_bbox[2])
                            for sp in line.get("spans", []):
                                s_text = sp.get("text", "").strip()
                                if not s_text:
                                    continue
                                sz = sp.get("size")
                                if sz:
                                    sizes.append(sz)
                                c_int = sp.get("color")
                                if c_int is not None:
                                    colors.append([
                                        round((c_int >> 16 & 255) / 255.0, 3),
                                        round((c_int >> 8 & 255) / 255.0, 3),
                                        round((c_int & 255) / 255.0, 3)
                                    ])
                                flags = sp.get("flags", 0)
                                fn = sp.get("font", "").lower()
                                if (flags & (1 << 4)) or any(w in fn for w in ("bold", "black", "heavy")):
                                    is_bold = True
                                if (flags & (1 << 1)) or any(w in fn for w in ("italic", "oblique")):
                                    is_italic = True

                        if sizes:
                            font_size = round(sum(sizes) / len(sizes), 1)
                        if colors:
                            font_color = colors[0]

                        # Detect alignment relative to block bounds
                        if line_x_starts and line_x_ends:
                            b_mid = (b_bbox[0] + b_bbox[2]) / 2.0
                            l_mids = [(s + e) / 2.0 for s, e in zip(line_x_starts, line_x_ends)]
                            avg_l_mid = sum(l_mids) / len(l_mids)
                            if abs(avg_l_mid - b_mid) < 3.0 and (b_bbox[2] - b_bbox[0]) > 40:
                                align = 1  # center
                            elif abs(max(line_x_ends) - b_bbox[2]) < 4.0 and abs(min(line_x_starts) - b_bbox[0]) > 8.0:
                                align = 2  # right

                    # Multi-point median background sampling: eliminate white patches while avoiding border/shadow noise
                    bg_color = [1.0, 1.0, 1.0]
                    try:
                        clip_rect = fitz.Rect(b_bbox)
                        if clip_rect.width > 2 and clip_rect.height > 2:
                            pix = page.get_pixmap(clip=clip_rect)
                            pw, ph = pix.width, pix.height
                            # Sample 6 boundary points inset from edges
                            sample_coords = [
                                (min(1, pw - 1), min(1, ph - 1)),
                                (max(0, pw - 2), min(1, ph - 1)),
                                (min(1, pw - 1), max(0, ph - 2)),
                                (max(0, pw - 2), max(0, ph - 2)),
                                (pw // 2, min(1, ph - 1)),
                                (min(1, pw - 1), ph // 2)
                            ]
                            sampled_colors = []
                            for sx, sy in sample_coords:
                                if 0 <= sx < pw and 0 <= sy < ph:
                                    p = pix.pixel(sx, sy)
                                    if len(p) >= 3:
                                        sampled_colors.append((p[0], p[1], p[2]))
                            if sampled_colors:
                                med_r = sorted(c[0] for c in sampled_colors)[len(sampled_colors) // 2]
                                med_g = sorted(c[1] for c in sampled_colors)[len(sampled_colors) // 2]
                                med_b = sorted(c[2] for c in sampled_colors)[len(sampled_colors) // 2]
                                bg_color = [round(med_r / 255.0, 3), round(med_g / 255.0, 3), round(med_b / 255.0, 3)]
                    except Exception:
                        pass

                    loc_payload = {
                        "type": "pdf_text_block",
                        "page_index": page_idx,
                        "block_no": b_no,
                        "bbox": b_bbox,
                        "font_size": font_size,
                        "font_color": font_color,
                        "is_bold": is_bold,
                        "is_italic": is_italic,
                        "align": align,
                        "bg_color": bg_color
                    }

                    segments.append(ParsedSegment(
                        segment_index=segment_index,
                        source_text=protected_text,
                        location=loc_payload,
                        protected_tokens=token_map,
                        context_hint=f"PDF Page {page_idx + 1}",
                        formatting_meta=loc_payload
                    ))
                    segment_index += 1

            # Detect scanned page (if page has images but almost zero extractable text)
            images = page.get_images()
            if images and page_text_len < 15:
                scanned_pages.append(page_idx + 1)

        # 3. Parse Document Outline / Bookmarks (TOC)
        try:
            toc = doc.get_toc()
            for toc_idx, toc_item in enumerate(toc):
                title = (toc_item[1] or "").strip()
                if title:
                    p_text, t_map = TokenProtector.protect_tokens(title)
                    segments.append(ParsedSegment(
                        segment_index=segment_index,
                        source_text=p_text,
                        location={
                            "type": "pdf_toc",
                            "toc_index": toc_idx,
                            "level": toc_item[0],
                            "page": toc_item[2]
                        },
                        protected_tokens=t_map,
                        context_hint="PDF Bookmarks / Outline",
                        formatting_meta={"is_toc": True}
                    ))
                    segment_index += 1
        except Exception:
            pass

        metadata = {
            "unit_count": len(doc),
            "unit_label": "pages",
            "page_count": len(doc),
            "scanned_pages": scanned_pages,
            "is_scanned_pdf": len(scanned_pages) > 0,
            "total_segments": len(segments)
        }
        return segments, metadata
