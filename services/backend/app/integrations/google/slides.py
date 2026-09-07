import asyncio
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from app.core.logging import logger
from app.documents.segmenter import ParsedSegment, TokenProtector
from app.integrations.google.slides_ast_sync import (
    GoogleSlidesASTParser,
    SlideASTNode,
    SlideDiffOp,
    SlideDiffOpType,
    SlideElementType,
    SlideMyersDiffEngine,
    SlideReverseIndexBatchPlanner,
)

SLIDES_API_BASE = "https://slides.googleapis.com/v1/presentations"


class GoogleSlidesService:
    """Manages Google Slides structured extraction, speaker notes, and SOTA in-place synchronization via real Google Slides API."""

    @classmethod
    async def get_presentation(cls, access_token: str, presentation_id: str, is_mock: bool = False) -> Dict[str, Any]:
        """Fetches presentation slides JSON with automatic retry."""
        if is_mock:
            return {
                "presentationId": presentation_id,
                "title": "Mock Presentation",
                "slides": []
            }

        headers = {"Authorization": f"Bearer {access_token}"}
        last_err = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=35.0) as http:
                    resp = await http.get(f"{SLIDES_API_BASE}/{presentation_id}", headers=headers)
                    if resp.status_code == 200:
                        return resp.json()
                    elif resp.status_code in (429, 500, 502, 503, 504):
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    else:
                        logger.error(f"Failed to fetch Google Slide: {resp.text}")
                        raise ValueError(f"Failed to fetch Google Slide: {resp.text}")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as net_err:
                last_err = net_err
                logger.warning(f"Transient connection error fetching Google Slide (attempt {attempt + 1}/4): {net_err}")
                await asyncio.sleep(1.5 * (attempt + 1))
            except Exception as e:
                last_err = e
                raise
        raise RuntimeError(f"Could not fetch Google Slide {presentation_id} after 4 attempts: {last_err}")

    @classmethod
    def parse_segments(
        cls,
        presentation_data: Dict[str, Any],
        translate_notes: bool = True
    ) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        """Extracts text from shapes, tables, and speaker notes per slide with precise object IDs."""
        segments: List[ParsedSegment] = []
        slides = presentation_data.get("slides", [])
        total_shapes = 0
        total_tables = 0
        total_notes = 0

        segment_idx = 0
        for s_idx, slide in enumerate(slides):
            slide_num = s_idx + 1
            slide_id = slide.get("objectId") or f"slide_{s_idx}"
            elements = slide.get("pageElements", [])

            for el_idx, el in enumerate(elements):
                el_obj_id = el.get("objectId") or f"el_{el_idx}"

                # 1. Shapes
                shape = el.get("shape")
                if shape:
                    text_content = shape.get("text", {})
                    text_elements = text_content.get("textElements", [])
                    full_text = "".join(t.get("textRun", {}).get("content", "") for t in text_elements).strip()

                    if full_text:
                        total_shapes += 1
                        protected_text, tags = TokenProtector.protect(full_text)

                        segments.append(ParsedSegment(
                            segment_index=segment_idx,
                            source_text=protected_text,
                            location={
                                "type": "gslide_shape",
                                "slide_num": slide_num,
                                "element_id": el_idx,
                                "slide_id": slide_id,
                                "element_object_id": el_obj_id
                            },
                            protected_tokens=tags,
                            context_hint=f"Slide {slide_num}",
                            formatting_meta={}
                        ))
                        segment_idx += 1

                # 2. Tables
                table = el.get("table")
                if table:
                    for r_idx, row in enumerate(table.get("tableRows", [])):
                        for c_idx, cell in enumerate(row.get("tableCells", [])):
                            c_text_obj = cell.get("text", {})
                            cell_elements = c_text_obj.get("textElements", [])
                            cell_text = "".join(t.get("textRun", {}).get("content", "") for t in cell_elements).strip()

                            if cell_text:
                                total_tables += 1
                                protected_text, tags = TokenProtector.protect(cell_text)

                                segments.append(ParsedSegment(
                                    segment_index=segment_idx,
                                    source_text=protected_text,
                                    location={
                                        "type": "gslide_table_cell",
                                        "slide_num": slide_num,
                                        "element_id": el_idx,
                                        "slide_id": slide_id,
                                        "element_object_id": el_obj_id,
                                        "row": r_idx,
                                        "col": c_idx
                                    },
                                    protected_tokens=tags,
                                    context_hint=f"Slide {slide_num} Table [R{r_idx+1}, C{c_idx+1}]",
                                    formatting_meta={"is_table": True, "row": r_idx, "col": c_idx}
                                ))
                                segment_idx += 1

            # 3. Speaker Notes
            if translate_notes:
                notes_page = slide.get("slideProperties", {}).get("notesPage", {})
                notes_page_id = notes_page.get("objectId")
                note_elements = notes_page.get("pageElements", [])
                for n_idx, n_el in enumerate(note_elements):
                    n_obj_id = n_el.get("objectId") or f"note_el_{n_idx}"
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
                            location={
                                "type": "gslide_note",
                                "slide_num": slide_num,
                                "note_id": n_idx,
                                "slide_id": slide_id,
                                "notes_page_id": notes_page_id,
                                "element_object_id": n_obj_id
                            },
                            protected_tokens=tags,
                            context_hint=f"Slide {slide_num} Speaker Notes",
                            formatting_meta={"is_note": True}
                        ))
                        segment_idx += 1

        metadata = {
            "title": presentation_data.get("title", "Presentation"),
            "total_slides": len(slides),
            "total_shapes": total_shapes,
            "total_tables": total_tables,
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
        translations: List[Dict[str, Any]],
        is_mock: bool = False
    ):
        """Applies batch updates to shapes, tables, and notes in the translated presentation copy."""
        if is_mock or not translations:
            return

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        requests = []
        for item in translations:
            src = item.get("source_text", "").strip()
            tgt = item.get("translated_text", "").strip()
            slide_id = item.get("slide_id")

            if src and tgt and src != tgt:
                req: Dict[str, Any] = {
                    "replaceAllText": {
                        "containsText": {"matchCase": True, "text": src},
                        "replaceText": tgt
                    }
                }
                if slide_id:
                    req["replaceAllText"]["pageObjectIds"] = [slide_id]
                requests.append(req)

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

    @classmethod
    async def apply_smart_slide_sync_to_existing_presentation(
        cls,
        access_token: str,
        target_presentation_id: str,
        segments: List[Any],
        previous_segments: Optional[List[Any]] = None,
        source_presentation_id: Optional[str] = None,
        parent_folder_id: Optional[str] = None,
        source_lang: str = "vi",
        target_lang: str = "ja",
        ocr_engine: str = "paddleocr",
        translate_images: bool = True,
        provider: Any = None,
        is_mock: bool = False,
    ) -> Dict[str, Any]:
        """SOTA Slide AST Myers Diff & Scoped Mutation Sync for Google Slides:
        1. Parses source and target presentations into structured SlideASTNode trees.
        2. Computes Myers LCS diff identifying unchanged, modified, inserted, and deleted slides.
        3. SlideReverseIndexBatchPlanner orders deletions descending to eliminate slide index shift drift.
        4. Scoped replacements (replaceAllText with pageObjectIds: [slide_id]) eliminate cross-slide text collisions.
        5. Native replaceImage (CENTER_CROP) preserves exact slide geometry, dimensions, and aspect ratio after OCR.
        """
        if is_mock:
            return {"status": "success", "mutations_planned": len(segments)}

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        # 1. Fetch target presentation AST
        target_data = await cls.get_presentation(access_token, target_presentation_id, is_mock=is_mock)
        target_slides = GoogleSlidesASTParser.parse_presentation(target_data)

        # 2. Fetch or construct source presentation AST
        source_slides: List[SlideASTNode] = []
        if source_presentation_id:
            try:
                source_data = await cls.get_presentation(access_token, source_presentation_id, is_mock=is_mock)
                source_slides = GoogleSlidesASTParser.parse_presentation(source_data)
            except Exception as src_err:
                logger.error(f"Could not parse source presentation ({source_presentation_id}): {src_err}")
                raise RuntimeError(f"Failed to fetch source presentation ({source_presentation_id}): {src_err}")

        # If source_presentation_id not provided at all, use target_slides as base structure
        if not source_slides:
            source_slides = target_slides

        # 3. Compute hierarchical Slide Myers Diff
        diff_ops = SlideMyersDiffEngine.diff_slides(
            source_slides=source_slides,
            target_slides=target_slides,
            previous_segments=previous_segments
        )
        logger.info(f"Slide Myers Diff completed: {len(diff_ops)} slide operations detected.")

        # 4. Process slide images with OCR and in-place replacement
        image_replacements: Dict[str, str] = {}
        temp_uploaded_drive_files: List[str] = []

        if translate_images:
            async with httpx.AsyncClient(timeout=45.0) as http:
                for s in source_slides:
                    for el in s.elements:
                        if el.element_type == SlideElementType.IMAGE and el.image_url:
                            try:
                                img_res = await http.get(el.image_url)
                                if img_res.status_code != 200:
                                    img_res = await http.get(el.image_url, headers=headers)
                                if img_res.status_code == 200 and len(img_res.content) > 100:
                                    img_bytes = img_res.content
                                    try:
                                        from app.documents.ocr.image_translator import image_translator
                                        trans_bytes = await image_translator.process_image(
                                            image_bytes=img_bytes,
                                            src_lang=source_lang,
                                            tgt_lang=target_lang,
                                            ocr_engine=ocr_engine,
                                            provider=provider
                                        )
                                        if trans_bytes and trans_bytes != img_bytes:
                                            from app.integrations.google.drive import GoogleDriveService
                                            temp_filename = f"temp_slide_img_{uuid.uuid4().hex[:8]}.png"
                                            up_res = await GoogleDriveService.upload_file(
                                                access_token=access_token,
                                                filename=temp_filename,
                                                content_bytes=trans_bytes,
                                                mime_type="image/png",
                                                parent_folder_id=parent_folder_id
                                            )
                                            temp_id = up_res.get("id")
                                            if temp_id:
                                                temp_uploaded_drive_files.append(temp_id)
                                                # Set reader permission for Google Slides API to fetch image
                                                await http.post(
                                                    f"https://www.googleapis.com/drive/v3/files/{temp_id}/permissions?supportsAllDrives=true",
                                                    headers=headers,
                                                    json={"role": "reader", "type": "anyone"}
                                                )
                                                direct_url = f"https://lh3.googleusercontent.com/d/{temp_id}"
                                                image_replacements[el.element_id] = direct_url
                                                logger.info(f"Prepared OCR image replacement for slide element {el.element_id} -> {direct_url}")
                                    except Exception as ocr_err:
                                        logger.warning(f"Could not OCR translate slide image {el.element_id}: {ocr_err}")
                            except Exception as dl_err:
                                logger.debug(f"Could not download slide image {el.image_url}: {dl_err}")

        # 5. Plan Reverse-Index & Slide-Scoped batchUpdate requests
        batch_requests = SlideReverseIndexBatchPlanner.plan_batch_updates(
            diff_ops=diff_ops,
            segments=segments,
            previous_segments=previous_segments,
            image_replacements=image_replacements
        )

        logger.info(f"Generated {len(batch_requests)} Google Slides batchUpdate requests.")

        # 6. Execute batch updates in chunks of 50 requests
        if batch_requests:
            for i in range(0, len(batch_requests), 50):
                chunk = batch_requests[i:i + 50]
                chunk_success = False
                last_chunk_err = ""
                for attempt in range(4):
                    try:
                        async with httpx.AsyncClient(timeout=45.0) as http:
                            resp = await http.post(
                                f"{SLIDES_API_BASE}/{target_presentation_id}:batchUpdate",
                                headers=headers,
                                json={"requests": chunk}
                            )
                            if resp.status_code == 200:
                                chunk_success = True
                                break
                            elif resp.status_code in (429, 500, 502, 503):
                                await asyncio.sleep(2.0 * (attempt + 1))
                            else:
                                last_chunk_err = f"Google Slides batchUpdate returned {resp.status_code}: {resp.text}"
                                logger.error(last_chunk_err)
                                break
                    except Exception as req_err:
                        last_chunk_err = str(req_err)
                        if attempt == 3:
                            logger.error(f"Error applying Google Slides batchUpdate chunk: {req_err}")
                        await asyncio.sleep(1.5 * (attempt + 1))
                if not chunk_success:
                    raise RuntimeError(f"Failed to execute Google Slides batchUpdate chunk: {last_chunk_err}")

        return {
            "status": "success",
            "diff_operations": len(diff_ops),
            "batch_requests_executed": len(batch_requests),
            "images_replaced": len(image_replacements)
        }

    @classmethod
    async def translate_embedded_images_in_presentation(
        cls,
        access_token: str,
        presentation_id: str,
        parent_folder_id: Optional[str] = None,
        source_lang: str = "vi",
        target_lang: str = "ja",
        ocr_engine: str = "paddleocr",
        provider: Any = None,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Finds all images across all slides of a Google Presentation, translates them via ImageTranslator OCR,
        and replaces them in-place via Google Slides API replaceImage requests.
        """
        if is_mock:
            return {"status": "success", "images_translated": 0}

        from app.documents.ocr.image_translator import image_translator
        from app.integrations.google.drive import GoogleDriveService

        data = await cls.get_presentation(access_token, presentation_id, is_mock=is_mock)
        slides = data.get("slides", [])

        images_to_process: List[Tuple[str, str, str]] = [] # (slide_id, element_id, content_url)
        for s in slides:
            s_id = s.get("objectId")
            for el in s.get("pageElements", []):
                img = el.get("image")
                if img:
                    url = img.get("contentUrl") or img.get("sourceUrl")
                    if url:
                        images_to_process.append((s_id, el.get("objectId"), url))

        if not images_to_process:
            logger.info(f"No images found to translate in Google Slides {presentation_id}.")
            return {"status": "success", "images_translated": 0}

        logger.info(f"Found {len(images_to_process)} images in Google Slides {presentation_id} for OCR translation.")

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        replace_requests: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=60.0) as http:
            for s_id, el_id, img_url in images_to_process:
                try:
                    # Download image without Authorization header first (Google CDN pre-signed URL)
                    img_res = await http.get(img_url)
                    if img_res.status_code != 200:
                        img_res = await http.get(img_url, headers=headers)
                    if img_res.status_code != 200 or len(img_res.content) < 100:
                        continue

                    img_bytes = img_res.content
                    trans_bytes = await image_translator.process_image(
                        image_bytes=img_bytes,
                        src_lang=source_lang,
                        tgt_lang=target_lang,
                        ocr_engine=ocr_engine,
                        provider=provider
                    )

                    if not trans_bytes or trans_bytes == img_bytes:
                        continue

                    temp_filename = f"temp_slide_img_{uuid.uuid4().hex[:8]}.png"
                    up_res = await GoogleDriveService.upload_file(
                        access_token=access_token,
                        filename=temp_filename,
                        content_bytes=trans_bytes,
                        mime_type="image/png",
                        parent_folder_id=parent_folder_id
                    )
                    temp_id = up_res.get("id")
                    if not temp_id:
                        continue

                    await http.post(
                        f"https://www.googleapis.com/drive/v3/files/{temp_id}/permissions?supportsAllDrives=true",
                        headers=headers,
                        json={"role": "reader", "type": "anyone"}
                    )
                    direct_url = f"https://lh3.googleusercontent.com/d/{temp_id}"
                    replace_requests.append({
                        "replaceImage": {
                            "imageObjectId": el_id,
                            "url": direct_url,
                            "imageReplaceMethod": "CENTER_CROP"
                        }
                    })
                    logger.info(f"Prepared OCR replaceImage for slide {s_id} element {el_id} -> {direct_url}")
                except Exception as err:
                    logger.warning(f"Could not translate image {el_id} in presentation {presentation_id}: {err}")

        if replace_requests:
            for i in range(0, len(replace_requests), 50):
                chunk = replace_requests[i:i + 50]
                async with httpx.AsyncClient(timeout=45.0) as http:
                    resp = await http.post(
                        f"{SLIDES_API_BASE}/{presentation_id}:batchUpdate",
                        headers=headers,
                        json={"requests": chunk}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"Failed to batch replace images in presentation {presentation_id}: {resp.text}")

        return {"status": "success", "images_translated": len(replace_requests)}
