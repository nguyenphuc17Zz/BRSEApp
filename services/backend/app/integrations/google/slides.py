from typing import Dict, List, Any, Optional, Tuple
import httpx
from app.core.logging import logger
from app.documents.segmenter import TokenProtector, ParsedSegment

SLIDES_API_BASE = "https://slides.googleapis.com/v1/presentations"

class GoogleSlidesService:
    """Manages Google Slides structured extraction, speaker notes, and non-destructive copies via real Google Slides API."""

    @classmethod
    async def get_presentation(cls, access_token: str, presentation_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Fetches presentation slides JSON."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(f"{SLIDES_API_BASE}/{presentation_id}", headers=headers)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch Google Slide: {resp.text}")
                raise ValueError(f"Failed to fetch Google Slide: {resp.text}")
            return resp.json()

    @classmethod
    def parse_segments(
        cls,
        presentation_data: Dict[str, Any],
        translate_notes: bool = True
    ) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        """Extracts text from shapes, tables, and speaker notes per slide."""
        segments: List[ParsedSegment] = []
        slides = presentation_data.get("slides", [])
        total_shapes = 0
        total_notes = 0

        segment_idx = 0
        for s_idx, slide in enumerate(slides):
            slide_num = s_idx + 1
            elements = slide.get("pageElements", [])

            for el_idx, el in enumerate(elements):
                shape = el.get("shape", {})
                text_content = shape.get("text", {})
                text_elements = text_content.get("textElements", [])
                full_text = "".join(t.get("textRun", {}).get("content", "") for t in text_elements).strip()

                if full_text:
                    total_shapes += 1
                    protected_text, tags = TokenProtector.protect(full_text)

                    segments.append(ParsedSegment(
                        segment_index=segment_idx,
                        source_text=protected_text,
                        location={"type": "gslide_shape", "slide_num": slide_num, "element_id": el_idx},
                        protected_tokens=tags,
                        context_hint=f"Slide {slide_num}",
                        formatting_meta={}
                    ))
                    segment_idx += 1

            # Speaker Notes
            if translate_notes:
                notes_page = slide.get("slideProperties", {}).get("notesPage", {})
                note_elements = notes_page.get("pageElements", [])
                for n_idx, n_el in enumerate(note_elements):
                    n_shape = n_el.get("shape", {})
                    n_text = n_shape.get("text", {})
                    n_text_runs = n_text.get("textElements", [])
                    note_str = "".join(t.get("textRun", {}).get("content", "") for t in n_text_runs).strip()
                    if note_str:
                        total_notes += 1
                        p_note, tags = TokenProtector.protect(note_str)
                        segments.append(ParsedSegment(
                            segment_index=segment_idx,
                            source_text=p_note,
                            location={"type": "gslide_note", "slide_num": slide_num, "note_id": n_idx},
                            protected_tokens=tags,
                            context_hint=f"Slide {slide_num} Speaker Notes",
                            formatting_meta={"is_note": True}
                        ))
                        segment_idx += 1

        metadata = {
            "title": presentation_data.get("title", "Presentation"),
            "total_slides": len(slides),
            "total_shapes": total_shapes,
            "total_notes": total_notes,
            "total_segments": len(segments)
        }
        return segments, metadata

    @classmethod
    async def get_metadata(
        cls,
        access_token: str,
        presentation_id: str,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Returns slide count and segment count for frontend configuration."""
        data = await cls.get_presentation(access_token, presentation_id, is_mock=is_mock)
        segments, meta = cls.parse_segments(data, translate_notes=True)
        return {
            "title": meta.get("title", "Google Presentation"),
            "format": "gslide",
            "total_slides": meta.get("total_slides", 1),
            "total_segments": len(segments)
        }

    @classmethod
    async def apply_translations_to_copy(
        cls,
        access_token: str,
        copy_presentation_id: str,
        translations: List[Dict[str, str]],
        is_mock: bool = False
    ):
        """Applies batch updates to shapes and notes in the translated presentation copy."""
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
                        f"{SLIDES_API_BASE}/{copy_presentation_id}:batchUpdate",
                        headers=headers,
                        json={"requests": chunk}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"Failed to batch update Google Slide {copy_presentation_id}: {resp.text}")
