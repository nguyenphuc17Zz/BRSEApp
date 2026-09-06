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

            for b in blocks:
                # b[4] is text, b[6] is block_type (0 for text, 1 for image)
                if len(b) > 6 and b[6] == 0:
                    raw_text = b[4].strip()
                    if not raw_text:
                        continue

                    page_text_len += len(raw_text)
                    protected_text, token_map = TokenProtector.protect_tokens(raw_text)

                    segments.append(ParsedSegment(
                        segment_index=segment_index,
                        source_text=protected_text,
                        location={
                            "type": "pdf_text_block",
                            "page_index": page_idx,
                            "block_no": b[5],
                            "bbox": [round(coord, 2) for coord in b[:4]]
                        },
                        protected_tokens=token_map,
                        context_hint=f"PDF Page {page_idx + 1}",
                        formatting_meta={
                            "bbox": list(b[:4]),
                            "page_index": page_idx
                        }
                    ))
                    segment_index += 1

            # Detect scanned page (if page has images but almost zero extractable text)
            images = page.get_images()
            if images and page_text_len < 15:
                scanned_pages.append(page_idx + 1)

        metadata = {
            "unit_count": len(doc),
            "unit_label": "pages",
            "page_count": len(doc),
            "scanned_pages": scanned_pages,
            "is_scanned_pdf": len(scanned_pages) > 0,
            "total_segments": len(segments)
        }
        return segments, metadata
