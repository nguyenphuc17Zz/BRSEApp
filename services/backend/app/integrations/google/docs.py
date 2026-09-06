from typing import Dict, List, Any, Optional, Tuple
import httpx
from app.core.logging import logger
from app.documents.segmenter import TokenProtector, ParsedSegment

DOCS_API_BASE = "https://docs.googleapis.com/v1/documents"

class GoogleDocsService:
    """Manages Google Docs structured parsing, selection translation, and non-destructive copy rendering via real Google Docs API."""

    @classmethod
    async def get_document_content(cls, access_token: str, document_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Fetches structured document JSON from Google Docs v1 API."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(f"{DOCS_API_BASE}/{document_id}", headers=headers)
            if resp.status_code != 200:
                logger.error(f"Failed to get Google Doc {document_id}: {resp.text}")
                raise ValueError(f"Failed to fetch Google Doc: {resp.text}")
            return resp.json()

    @classmethod
    def parse_segments(cls, doc_data: Dict[str, Any]) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        """Parses Google Doc into standardized translatable segments with heading context."""
        segments: List[ParsedSegment] = []
        body = doc_data.get("body", {})
        content = body.get("content", [])
        current_heading = doc_data.get("title", "Document")
        segment_idx = 0

        for item in content:
            if "paragraph" in item:
                p = item["paragraph"]
                style = p.get("paragraphStyle", {}).get("namedStyleType", "")
                full_p_text = "".join(el.get("textRun", {}).get("content", "") for el in p.get("elements", [])).strip()
                if not full_p_text:
                    continue

                if "HEADING" in style:
                    current_heading = full_p_text

                protected_text, tags = TokenProtector.protect(full_p_text)

                segments.append(ParsedSegment(
                    segment_index=segment_idx,
                    source_text=protected_text,
                    location={"type": "paragraph", "p_index": segment_idx},
                    protected_tokens=tags,
                    context_hint=current_heading,
                    formatting_meta={"style": style}
                ))
                segment_idx += 1

        metadata = {
            "title": doc_data.get("title", "Document"),
            "revision_id": doc_data.get("revisionId", "1"),
            "total_segments": len(segments)
        }
        return segments, metadata

    @classmethod
    async def get_metadata(cls, access_token: str, document_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Returns document title and segment count for frontend configuration."""
        data = await cls.get_document_content(access_token, document_id, is_mock=is_mock)
        segments, meta = cls.parse_segments(data)
        return {
            "title": meta.get("title", "Google Doc"),
            "format": "gdoc",
            "total_segments": len(segments)
        }

    @classmethod
    async def apply_translations_to_copy(
        cls,
        access_token: str,
        copy_document_id: str,
        translations: List[Dict[str, str]],
        is_mock: bool = False
    ):
        """Applies batch updates to the translated copy via Google Docs API."""
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        requests = []
        for item in translations:
            src = item.get("source_text", "").strip()
            tgt = item.get("translated_text", "").strip()
            if src and tgt and src != tgt:
                requests.append({
                    "replaceAllText": {
                        "containsText": {"matchCase": True, "text": src},
                        "replaceText": tgt
                    }
                })

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
