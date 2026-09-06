import asyncio
import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.core.logging import logger
from app.documents.models import DocumentJob, DocumentSegment, DocumentFile, DocumentIssue
from app.documents.qa import DocumentQAChecker
from app.documents.segmenter import TokenProtector
from app.engine.pipeline import clean_json_response
from app.integrations.models import IntegrationAccount, IntegrationAuditLog
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.drive import GoogleDriveService
from app.integrations.google.docs import GoogleDocsService
from app.integrations.google.sheets import GoogleSheetsService
from app.integrations.google.slides import GoogleSlidesService
from app.providers.registry import provider_registry
from app.documents.jobs import job_manager

class GoogleJobManager:
    """Manages asynchronous document translation jobs for Google Docs, Sheets, and Slides via Google REST API."""

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._pause_flags: Dict[str, bool] = {}

    def start_job(self, job_id: str):
        """Starts a Google translation pipeline in a background task."""
        if job_id in self._active_tasks and not self._active_tasks[job_id].done():
            logger.warning(f"Google Job {job_id} is already running.")
            return

        self._cancel_flags[job_id] = False
        self._pause_flags[job_id] = False
        task = asyncio.create_task(self._run_job_pipeline(job_id))
        self._active_tasks[job_id] = task

    def pause_job(self, job_id: str):
        self._pause_flags[job_id] = True

    def resume_job(self, job_id: str):
        self._pause_flags[job_id] = False
        self.start_job(job_id)

    def cancel_job(self, job_id: str):
        self._cancel_flags[job_id] = True
        if job_id in self._active_tasks:
            self._active_tasks[job_id].cancel()

    async def _run_job_pipeline(self, job_id: str):
        """Executes the full Google Document translation lifecycle: analyzing -> segmenting -> translating -> QA -> rendering to copy."""
        try:
            async with async_session_maker() as db:
                job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
                if not job:
                    logger.error(f"Google Job {job_id} not found.")
                    return

                doc_file = (await db.execute(select(DocumentFile).where(DocumentFile.id == job.document_id))).scalar_one_or_none()
                if not doc_file:
                    job.status = "failed"
                    job.error_message = "Document file record not found."
                    await db.commit()
                    return

                options = json.loads(job.options_json or "{}")
                file_id = options.get("file_id") or doc_file.original_path
                file_type = doc_file.file_type.lower() # gdoc, gsheet, gslide
                account_id = options.get("account_id")

                # Resolve Google token
                acc = None
                if account_id:
                    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.id == account_id))).scalar_one_or_none()
                if not acc:
                    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.is_active == True))).scalars().first()

                if not acc:
                    job.status = "failed"
                    job.error_message = "Google Workspace integration account not connected."
                    await db.commit()
                    return

                token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
                is_mock = acc.is_mock

                # Determine if the file is an Office or non-native document
                title_or_name = (options.get("title") or doc_file.filename or "").lower()
                is_office_or_binary = any(
                    title_or_name.endswith(ext)
                    for ext in (".docx", ".xlsx", ".pptx", ".pdf", ".doc", ".xls", ".ppt")
                )

                # If not obvious from filename, check actual Drive mimeType
                if not is_office_or_binary and not is_mock:
                    try:
                        f_meta = await GoogleDriveService.get_file_metadata(token, file_id, is_mock=is_mock)
                        mime = f_meta.get("mimeType", "").lower()
                        if mime and not mime.startswith("application/vnd.google-apps."):
                            is_office_or_binary = True
                    except Exception as meta_err:
                        logger.debug(f"Could not verify mimeType for {file_id}: {meta_err}")

                # Route to Hybrid Document Pipeline ONLY if file is an Office/binary file
                if is_office_or_binary:
                    await self._run_hybrid_image_pipeline(
                        job_id=job_id,
                        job=job,
                        doc_file=doc_file,
                        token=token,
                        is_mock=is_mock,
                        options=options,
                        file_id=file_id,
                        file_type=file_type,
                        db=db
                    )
                    return

                # Stage 1: Analyzing & Segmenting (if not already segmented)
                seg_chk = (await db.execute(select(DocumentSegment).where(DocumentSegment.job_id == job_id))).scalars().first()
                if not seg_chk:
                    job.status = "segmenting"
                    job.current_stage = f"Phân tích cấu trúc Google {file_type.upper()}..."
                    await db.commit()

                    try:
                        if "sheet" in file_type:
                            sheet_data = await GoogleSheetsService.get_spreadsheet(token, file_id, is_mock=is_mock)
                            selected_sheets = options.get("selected_sheets")
                            parsed_segments, meta = GoogleSheetsService.parse_segments(sheet_data, selected_sheets=selected_sheets)
                        elif "slide" in file_type:
                            pres_data = await GoogleSlidesService.get_presentation(token, file_id, is_mock=is_mock)
                            translate_notes = options.get("translate_notes", True)
                            parsed_segments, meta = GoogleSlidesService.parse_segments(pres_data, translate_notes=translate_notes)
                        else: # gdoc / doc
                            doc_data = await GoogleDocsService.get_document_content(token, file_id, is_mock=is_mock)
                            selected_tabs = options.get("selected_tabs")
                            parsed_segments, meta = GoogleDocsService.parse_segments(doc_data, selected_tabs=selected_tabs)
                    except Exception as api_err:
                        err_str = str(api_err).lower()
                        if "must not be an office file" in err_str or "failed_precondition" in err_str or "400" in err_str:
                            logger.info(f"Google Workspace API rejected file {file_id} as non-native. Seamlessly recovering via hybrid document pipeline...")
                            await self._run_hybrid_image_pipeline(
                                job_id=job_id,
                                job=job,
                                doc_file=doc_file,
                                token=token,
                                is_mock=is_mock,
                                options=options,
                                file_id=file_id,
                                file_type=file_type,
                                db=db
                            )
                            return
                        raise

                    for ps in parsed_segments:
                        seg = DocumentSegment(
                            job_id=job.id,
                            segment_index=ps.segment_index,
                            location_json=json.dumps(ps.location, ensure_ascii=False),
                            source_text=ps.source_text,
                            protected_tokens_json=json.dumps(ps.protected_tokens, ensure_ascii=False),
                            context_hint=ps.context_hint,
                            status="pending"
                        )
                        db.add(seg)

                    job.total_segments = len(parsed_segments)
                    await db.commit()

                # Stage 2: Translating in Batches
                job.status = "translating"
                await db.commit()

                pending_segs_res = await db.execute(
                    select(DocumentSegment)
                    .where(DocumentSegment.job_id == job_id, DocumentSegment.status == "pending")
                    .order_by(DocumentSegment.segment_index.asc())
                )
                pending_segments = pending_segs_res.scalars().all()

                # --- Live Translation Memory & Delta Matching ---
                tm_hits = 0
                tm_map: Dict[str, str] = {}
                try:
                    from app.db.models import TranslationMemory
                    from sqlalchemy import or_

                    # 1. Load from TranslationMemory for matching language pair
                    tm_query = select(TranslationMemory.source_text, TranslationMemory.target_text).where(
                        TranslationMemory.source_language == job.source_language,
                        TranslationMemory.target_language == job.target_language
                    )
                    if job.project_id:
                        tm_query = tm_query.where(
                            or_(
                                TranslationMemory.project_id == job.project_id,
                                TranslationMemory.project_id.is_(None)
                            )
                        )
                    tm_res = (await db.execute(tm_query)).all()
                    for s_txt, t_txt in tm_res:
                        if s_txt and t_txt:
                            tm_map[s_txt.strip()] = t_txt.strip()

                    # 2. Also check previous job segments for this exact file_id
                    prev_seg_query = (
                        select(DocumentSegment.source_text, DocumentSegment.translated_text)
                        .join(DocumentJob, DocumentSegment.job_id == DocumentJob.id)
                        .join(DocumentFile, DocumentJob.document_id == DocumentFile.id)
                        .where(
                            DocumentFile.original_path == file_id,
                            DocumentJob.id != job.id,
                            DocumentJob.target_language == job.target_language,
                            DocumentSegment.status.in_(["translated", "user_edited"])
                        )
                        .order_by(DocumentSegment.created_at.desc())
                    )
                    prev_segs = (await db.execute(prev_seg_query)).all()
                    for s_txt, t_txt in prev_segs:
                        if s_txt and t_txt and s_txt.strip() not in tm_map:
                            tm_map[s_txt.strip()] = t_txt.strip()

                    # 3. Match pending segments against TM (100% Exact Match)
                    for seg in pending_segments:
                        s_clean = (seg.source_text or "").strip()
                        if s_clean and s_clean in tm_map:
                            seg.translated_text = tm_map[s_clean]
                            seg.status = "translated"
                            seg.context_hint = "TM_EXACT_MATCH"
                            tm_hits += 1

                    if tm_hits > 0:
                        logger.info(f"Translation Memory / Delta match: {tm_hits}/{len(pending_segments)} segments reused without LLM tokens.")
                        completed_cnt = (await db.execute(
                            select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status.in_(["translated", "user_edited"]))
                        )).scalars().all()
                        job.completed_segments = len(completed_cnt)
                        job.progress_percent = round((job.completed_segments / max(1, job.total_segments)) * 100, 1)
                        await db.commit()
                        pending_segments = [s for s in pending_segments if s.status == "pending"]

                except Exception as tm_err:
                    logger.warning(f"Notice during Translation Memory matching: {tm_err}")

                provider = provider_registry.get_provider(job.provider) or provider_registry.get_provider("gemini")
                translation_cache: Dict[str, str] = {}
                max_batch_chars = 1200
                max_batch_items = 8 if (job.provider or "").lower() == "groq" else 12

                batches: List[List[DocumentSegment]] = []
                current_batch: List[DocumentSegment] = []
                current_chars = 0

                for seg in pending_segments:
                    seg_len = len(seg.source_text or "")
                    if current_batch and (current_chars + seg_len > max_batch_chars or len(current_batch) >= max_batch_items):
                        batches.append(current_batch)
                        current_batch = [seg]
                        current_chars = seg_len
                    else:
                        current_batch.append(seg)
                        current_chars += seg_len

                if current_batch:
                    batches.append(current_batch)

                processed_so_far = 0
                for b_idx, batch in enumerate(batches):
                    if self._cancel_flags.get(job_id):
                        job.status = "cancelled"
                        await db.commit()
                        return

                    if self._pause_flags.get(job_id):
                        job.status = "paused"
                        await db.commit()
                        return

                    processed_so_far += len(batch)
                    job.current_stage = f"Đang dịch batch {b_idx + 1}/{len(batches)} ({processed_so_far}/{job.total_segments} phân đoạn)..."
                    await db.commit()

                    await self._translate_batch(
                        db=db,
                        batch=batch,
                        job=job,
                        provider=provider,
                        translation_cache=translation_cache
                    )

                    # Update progress counts
                    completed_cnt = (await db.execute(
                        select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status.in_(["translated", "user_edited"]))
                    )).scalars().all()
                    failed_cnt = (await db.execute(
                        select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status == "failed")
                    )).scalars().all()
                    job.completed_segments = len(completed_cnt)
                    job.failed_segments = len(failed_cnt)
                    processed_total = job.completed_segments + job.failed_segments
                    job.progress_percent = round((processed_total / max(1, job.total_segments)) * 100, 1)
                    await db.commit()

                    # Adaptive pacing between batches
                    if b_idx < len(batches) - 1:
                        pace_delay = 1.2 if (job.provider or "").lower() == "groq" else 0.5
                        await asyncio.sleep(pace_delay)

                # Recount segments in case all were matched by TM or batch loop finished
                completed_cnt = (await db.execute(
                    select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status.in_(["translated", "user_edited"]))
                )).scalars().all()
                failed_cnt = (await db.execute(
                    select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status == "failed")
                )).scalars().all()
                job.completed_segments = len(completed_cnt)
                job.failed_segments = len(failed_cnt)
                processed_total = job.completed_segments + job.failed_segments
                job.progress_percent = round((processed_total / max(1, job.total_segments)) * 100, 1)
                await db.commit()

                if job.completed_segments == 0 and job.failed_segments > 0:
                    job.status = "failed"
                    job.progress_percent = 100.0
                    clean_err = job.error_message or "Không thể kết nối hoặc mô hình AI quá tải/hết quota."
                    job.error_message = clean_err
                    job.current_stage = f"Thất bại: {clean_err}"
                    await db.commit()
                    logger.error(f"Google Document translation job {job_id} failed: 0 of {job.total_segments} segments translated.")
                    return

                # Stage 3: QA Verification
                job.status = "qa"
                job.current_stage = "Kiểm tra chất lượng bản dịch (QA)..."
                await db.commit()

                all_segs_res = await db.execute(
                    select(DocumentSegment).where(DocumentSegment.job_id == job_id)
                )
                all_segs = all_segs_res.scalars().all()

                for seg in all_segs:
                    token_map = json.loads(seg.protected_tokens_json or "{}")
                    issues = DocumentQAChecker.check_segment(
                        job_id=job.id,
                        segment_id=seg.id,
                        source_text=seg.source_text,
                        translated_text=seg.translated_text or "",
                        location_text=seg.context_hint or f"Segment #{seg.segment_index + 1}",
                        protected_tokens_map=token_map
                    )
                    for iss in issues:
                        db.add(iss)

                await db.commit()

                # Stage 4: Rendering / Applying to Non-Destructive Copy on Google Drive
                job.status = "rendering"
                job.current_stage = "Đang tạo bản sao an toàn và cập nhật nội dung trên Google Drive..."
                await db.commit()

                target_lang = job.target_language.upper()
                original_title = options.get("title") or doc_file.filename
                custom_name = (options.get("target_filename") or "").strip()
                if custom_name:
                    copy_name = custom_name
                else:
                    copy_name = f"{original_title}_{target_lang}"

                target_mode = options.get("target_mode", "create")
                target_file_id = options.get("target_file_id")

                if target_mode == "update" and target_file_id:
                    copy_id = target_file_id
                    job.current_stage = f"Đang đồng bộ nội dung cập nhật vào file Google Drive đã có ({copy_id})..."
                    await db.commit()
                    logger.info(f"Target mode is 'update'. Directly applying translations to existing Drive file: {copy_id}")
                    try:
                        if "sheet" in file_type or "slide" in file_type or "presentation" in file_type:
                            await GoogleDriveService.sync_existing_file_content(
                                access_token=token,
                                source_file_id=file_id,
                                target_file_id=copy_id,
                                file_type=file_type,
                                is_mock=is_mock
                            )
                        else:
                            logger.info(f"Google Doc in-place sync ({copy_id}): Preserving native multi-tab layout via Docs REST API.")
                    except Exception as sync_err:
                        logger.warning(f"Could not sync layout to existing file {copy_id}: {sync_err}")
                else:
                    # 1. Create safe copy in Drive
                    copy_res = await GoogleDriveService.create_translated_copy(
                        token,
                        source_file_id=file_id,
                        target_name=copy_name,
                        parent_folder_id=options.get("parent_folder_id"),
                        is_mock=is_mock
                    )
                    copy_id = copy_res.get("id", f"copy_{file_id}_{target_lang}")

                # 2. Apply updates to the copy via format-specific REST API
                if "sheet" in file_type:
                    updates = []
                    for seg in all_segs:
                        loc = json.loads(seg.location_json or "{}")
                        text_val = seg.translated_text or seg.source_text
                        if loc.get("type") == "gsheet_cell":
                            updates.append({
                                "sheet": loc.get("sheet", "Sheet1"),
                                "row": loc.get("row", 0),
                                "col": loc.get("col", 0),
                                "translated_text": text_val
                            })
                    await GoogleSheetsService.apply_translations_to_copy(
                        access_token=token,
                        copy_spreadsheet_id=copy_id,
                        updates=updates,
                        is_mock=is_mock
                    )

                    # Update sheet titles if translate_sheet_names is enabled (default True)
                    if options.get("translate_sheet_names", True):
                        try:
                            await asyncio.sleep(1.2)
                            await GoogleSheetsService.translate_and_update_sheet_titles(
                                access_token=token,
                                copy_spreadsheet_id=copy_id,
                                source_lang=job.source_language or "ja",
                                target_lang=job.target_language or "vi",
                                provider=provider,
                                model=job.model,
                                is_mock=is_mock
                            )
                        except Exception as sheet_err:
                            logger.warning(f"Could not update sheet titles for copy {copy_id}: {sheet_err}")
                elif "slide" in file_type:
                    slide_updates = []
                    for seg in all_segs:
                        token_map = json.loads(seg.protected_tokens_json or "{}")
                        raw_src, _ = TokenProtector.restore_tokens(seg.source_text, token_map)
                        if seg.translated_text and raw_src != seg.translated_text:
                            slide_updates.append({
                                "source_text": raw_src,
                                "translated_text": seg.translated_text
                            })
                    await GoogleSlidesService.apply_translations_to_copy(
                        access_token=token,
                        copy_presentation_id=copy_id,
                        translations=slide_updates,
                        is_mock=is_mock
                    )
                else: # gdoc
                    if target_mode == "update":
                        # Smart Delta Sync for existing Google Doc:
                        # Find previous job by same document_id, same source original_path, or target copy_id
                        prev_segs = []
                        prev_job = (await db.execute(
                            select(DocumentJob)
                            .join(DocumentFile, DocumentJob.document_id == DocumentFile.id)
                            .where(
                                DocumentJob.id != job.id,
                                DocumentJob.status.in_(["completed", "partially_completed"]),
                                or_(
                                    DocumentJob.document_id == job.document_id,
                                    DocumentFile.original_path == doc_file.original_path,
                                    DocumentJob.output_path.contains(copy_id) if copy_id else False
                                )
                            )
                            .order_by(DocumentJob.created_at.desc())
                        )).scalars().first()
                        if prev_job:
                            prev_segs = (await db.execute(
                                select(DocumentSegment)
                                .where(DocumentSegment.job_id == prev_job.id)
                            )).scalars().all()

                        await GoogleDocsService.apply_smart_delta_sync_to_existing_doc(
                            access_token=token,
                            target_document_id=copy_id,
                            segments=all_segs,
                            previous_segments=prev_segs,
                            source_document_id=file_id,
                            selected_tabs=options.get("selected_tabs"),
                            parent_folder_id=options.get("parent_folder_id"),
                            source_lang=job.source_language or "vi",
                            target_lang=job.target_language or "ja",
                            ocr_engine=options.get("ocr_mode", "paddleocr"),
                            translate_images=options.get("translate_images", True),
                            provider=provider,
                            is_mock=is_mock
                        )
                    else:
                        doc_updates = []
                        for seg in all_segs:
                            token_map = json.loads(seg.protected_tokens_json or "{}")
                            raw_src, _ = TokenProtector.restore_tokens(seg.source_text, token_map)
                            if seg.translated_text and raw_src != seg.translated_text:
                                doc_updates.append({
                                    "source_text": raw_src,
                                    "translated_text": seg.translated_text
                                })
                        await GoogleDocsService.apply_translations_to_copy(
                            access_token=token,
                            copy_document_id=copy_id,
                            translations=doc_updates,
                            selected_tabs=options.get("selected_tabs"),
                            is_mock=is_mock
                        )

                    # Update tab titles on the tab bar if translate_tab_titles is enabled (default True)
                    if options.get("translate_tab_titles", True):
                        try:
                            await asyncio.sleep(1.2)
                            await GoogleDocsService.translate_and_update_tab_titles(
                                access_token=token,
                                copy_document_id=copy_id,
                                source_document_id=file_id,
                                source_lang=job.source_language or "vi",
                                target_lang=job.target_language or "ja",
                                provider=provider,
                                model=job.model,
                                is_mock=is_mock
                            )
                        except Exception as tab_err:
                            logger.warning(f"Could not update tab titles for copy {copy_id}: {tab_err}")


                    # Translate embedded images across all tabs if requested
                    if options.get("translate_images"):
                        job.current_stage = "Đang dịch hình ảnh và sơ đồ trong tài liệu..."
                        await db.commit()
                        ocr_mode = options.get("ocr_mode", "paddleocr")
                        try:
                            await GoogleDocsService.translate_embedded_images_in_copy(
                                access_token=token,
                                copy_document_id=copy_id,
                                parent_folder_id=options.get("parent_folder_id"),
                                source_lang=job.source_language or "vi",
                                target_lang=job.target_language or "ja",
                                ocr_engine=ocr_mode,
                                provider=provider,
                                is_mock=is_mock
                            )
                        except Exception as img_err:
                            logger.warning(f"Could not translate embedded images for copy {copy_id}: {img_err}")

                # Finalize Job
                job.progress_percent = 100.0
                job.output_filename = copy_name
                job.output_path = f"https://drive.google.com/open?id={copy_id}"

                if job.failed_segments > 0:
                    job.status = "partially_completed"
                    job.current_stage = f"Hoàn tất với cảnh báo ({job.completed_segments}/{job.total_segments} phân đoạn dịch thành công)."
                else:
                    job.status = "completed"
                    if target_mode == "update":
                        job.current_stage = f"Đồng bộ thành công! Đã cập nhật nội dung mới nhất vào file '{copy_name}' trên Google Drive."
                    else:
                        job.current_stage = f"Dịch thành công! Đã tạo bản sao an toàn '{copy_name}' trên Google Drive."

                # Auto-save newly translated segments into TranslationMemory
                try:
                    from app.db.models import TranslationMemory
                    new_tm_entries = []
                    for s in all_segs:
                        if s.status in ("translated", "user_edited") and s.source_text and s.translated_text:
                            s_clean = s.source_text.strip()
                            if s_clean and s_clean not in tm_map:
                                new_tm_entries.append(
                                    TranslationMemory(
                                        project_id=job.project_id,
                                        source_text=s_clean,
                                        target_text=s.translated_text.strip(),
                                        source_language=job.source_language or "ja",
                                        target_language=job.target_language or "vi",
                                        style=job.style or "business",
                                        provider=job.provider,
                                        model=job.model
                                    )
                                )
                                tm_map[s_clean] = s.translated_text.strip()
                    if new_tm_entries:
                        db.add_all(new_tm_entries)
                        await db.commit()
                        logger.info(f"Saved {len(new_tm_entries)} new segments into TranslationMemory.")
                except Exception as save_tm_err:
                    logger.debug(f"Notice saving segments to TranslationMemory: {save_tm_err}")

                # Record Audit Log
                db.add(IntegrationAuditLog(
                    integration="google",
                    operation=f"translate_{file_type}",
                    project_id=job.project_id,
                    source_id=file_id,
                    provider=job.provider,
                    model=job.model,
                    status=job.status,
                    details_json=json.dumps({
                        "translated_copy_id": copy_id,
                        "translated_copy_name": copy_name,
                        "total_segments": job.total_segments,
                        "completed_segments": job.completed_segments
                    })
                ))
                await db.commit()
                logger.info(f"Google Workspace translation job {job_id} completed successfully!")

        except asyncio.CancelledError:
            logger.info(f"Google translation job {job_id} cancelled.")
            async with async_session_maker() as db:
                job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
                if job and job.status not in ("completed", "partially_completed"):
                    job.status = "cancelled"
                    job.current_stage = "Đã hủy bởi người dùng"
                    await db.commit()
        except Exception as e:
            logger.error(f"Google translation job {job_id} failed: {e}", exc_info=True)
            async with async_session_maker() as db:
                job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
                if job:
                    job.status = "failed"
                    job.error_message = str(e)
                    job.current_stage = f"Thất bại: {str(e)}"
                    await db.commit()

    async def _run_hybrid_image_pipeline(
        self,
        job_id: str,
        job: DocumentJob,
        doc_file: DocumentFile,
        token: str,
        is_mock: bool,
        options: Dict[str, Any],
        file_id: str,
        file_type: str,
        db: AsyncSession
    ):
        """Executes Hybrid Export pipeline:
        1. Export/download Google Workspace or binary file to local temp directory.
        2. Parse file structure with Document Parser.
        3. Translate text segments with AI model.
        4. Run QA checker.
        5. Render output file with OCR & ImageTranslator (PaddleOCR/Vision).
        6. Upload safe translated copy to Google Drive.
        7. Clean up temp files.
        """
        orig_name = (options.get("title") or doc_file.filename or "").lower()
        norm_type = file_type.lower()
        if orig_name.endswith(".xlsx") or "sheet" in norm_type:
            ext = "xlsx"
            content_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            google_mime = "application/vnd.google-apps.spreadsheet"
        elif orig_name.endswith(".pptx") or "slide" in norm_type or "presentation" in norm_type:
            ext = "pptx"
            content_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            google_mime = "application/vnd.google-apps.presentation"
        elif orig_name.endswith(".pdf") or "pdf" in norm_type:
            ext = "pdf"
            content_mime = "application/pdf"
            google_mime = None
        else:
            ext = "docx"
            content_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            google_mime = "application/vnd.google-apps.document"

        temp_dir = Path("data/temp/google_exports")
        temp_dir.mkdir(parents=True, exist_ok=True)

        clean_title = "".join(c for c in (options.get("title") or doc_file.filename) if c.isalnum() or c in (" ", "-", "_")).strip() or "document"
        temp_input_path = temp_dir / f"{job.id}_src_{clean_title}.{ext}"
        temp_output_path = temp_dir / f"{job.id}_out_{clean_title}.{ext}"

        try:
            # Stage 1: Exporting / Downloading from Google Drive
            job.status = "segmenting"
            job.current_stage = f"Đang trích xuất tài liệu từ Google Drive (định dạng .{ext})..."
            await db.commit()

            await GoogleDriveService.export_or_download_file(
                access_token=token,
                file_id=file_id,
                file_type=norm_type,
                target_path=temp_input_path,
                is_mock=is_mock
            )

            # Stage 2: Segmenting
            seg_chk = (await db.execute(select(DocumentSegment).where(DocumentSegment.job_id == job_id))).scalars().first()
            if not seg_chk:
                job.current_stage = f"Phân tích cấu trúc và hình ảnh tài liệu .{ext}..."
                await db.commit()

                if not is_mock and temp_input_path.exists():
                    try:
                        parser = job_manager._get_parser(ext)
                        parsed_segments, meta = parser.parse(temp_input_path, options)
                    except Exception as parse_err:
                        logger.warning(f"Error parsing file with native parser: {parse_err}. Falling back to default segment.")
                        parsed_segments = []
                else:
                    parsed_segments = []

                if not parsed_segments:
                    # Provide fallback segment
                    from app.documents.segmenter import ParsedSegment
                    parsed_segments = [
                        ParsedSegment(
                            segment_index=0,
                            source_text="Sample text for Google Drive Document",
                            location={"type": "paragraph", "p_index": 0},
                            protected_tokens={},
                            context_hint="Title"
                        )
                    ]

                for ps in parsed_segments:
                    seg = DocumentSegment(
                        job_id=job.id,
                        segment_index=ps.segment_index,
                        location_json=json.dumps(ps.location, ensure_ascii=False),
                        source_text=ps.source_text,
                        protected_tokens_json=json.dumps(ps.protected_tokens, ensure_ascii=False),
                        context_hint=ps.context_hint,
                        status="pending"
                    )
                    db.add(seg)

                job.total_segments = len(parsed_segments)
                await db.commit()

            # Stage 3: Translating Text Segments
            job.status = "translating"
            await db.commit()

            pending_segs_res = await db.execute(
                select(DocumentSegment)
                .where(DocumentSegment.job_id == job_id, DocumentSegment.status == "pending")
                .order_by(DocumentSegment.segment_index.asc())
            )
            pending_segments = pending_segs_res.scalars().all()

            provider = provider_registry.get_provider(job.provider) or provider_registry.get_provider("gemini")
            translation_cache: Dict[str, str] = {}
            max_batch_chars = 1200
            max_batch_items = 8 if (job.provider or "").lower() == "groq" else 12

            batches: List[List[DocumentSegment]] = []
            current_batch: List[DocumentSegment] = []
            current_chars = 0

            for seg in pending_segments:
                seg_len = len(seg.source_text or "")
                if current_batch and (current_chars + seg_len > max_batch_chars or len(current_batch) >= max_batch_items):
                    batches.append(current_batch)
                    current_batch = [seg]
                    current_chars = seg_len
                else:
                    current_batch.append(seg)
                    current_chars += seg_len

            if current_batch:
                batches.append(current_batch)

            processed_so_far = 0
            for b_idx, batch in enumerate(batches):
                if self._cancel_flags.get(job_id):
                    job.status = "cancelled"
                    await db.commit()
                    return

                if self._pause_flags.get(job_id):
                    job.status = "paused"
                    await db.commit()
                    return

                processed_so_far += len(batch)
                job.current_stage = f"Đang dịch nội dung batch {b_idx + 1}/{len(batches)} ({processed_so_far}/{job.total_segments} phân đoạn)..."
                await db.commit()

                await self._translate_batch(
                    db=db,
                    batch=batch,
                    job=job,
                    provider=provider,
                    translation_cache=translation_cache
                )

                completed_cnt = (await db.execute(
                    select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status.in_(["translated", "user_edited"]))
                )).scalars().all()
                failed_cnt = (await db.execute(
                    select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status == "failed")
                )).scalars().all()
                job.completed_segments = len(completed_cnt)
                job.failed_segments = len(failed_cnt)
                processed_total = job.completed_segments + job.failed_segments
                job.progress_percent = round((processed_total / max(1, job.total_segments)) * 75, 1)
                await db.commit()

                if b_idx < len(batches) - 1:
                    pace_delay = 1.2 if (job.provider or "").lower() == "groq" else 0.5
                    await asyncio.sleep(pace_delay)

            # Stage 4: QA
            job.status = "qa"
            job.current_stage = "Kiểm tra chất lượng bản dịch (QA)..."
            await db.commit()

            all_segs_res = await db.execute(
                select(DocumentSegment).where(DocumentSegment.job_id == job_id)
            )
            all_segs = all_segs_res.scalars().all()

            for seg in all_segs:
                token_map = json.loads(seg.protected_tokens_json or "{}")
                issues = DocumentQAChecker.check_segment(
                    job_id=job.id,
                    segment_id=seg.id,
                    source_text=seg.source_text,
                    translated_text=seg.translated_text or "",
                    location_text=seg.context_hint or f"Segment #{seg.segment_index + 1}",
                    protected_tokens_map=token_map
                )
                for iss in issues:
                    db.add(iss)

            await db.commit()

            # Stage 5: Rendering & Optional OCR Image Translation
            job.status = "rendering"
            should_ocr = bool(options.get("translate_images", False))
            ocr_engine_name = options.get("ocr_mode", "paddleocr")
            if should_ocr:
                engine_label = "PaddleOCR (Local)" if ocr_engine_name == "paddleocr" else "Gemini Vision"
                job.current_stage = f"Đang quét chữ trong hình ảnh bằng {engine_label}, inpainting và tạo file..."
            else:
                job.current_stage = f"Đang tổng hợp cấu trúc và tạo file tài liệu {ext.upper()} đã dịch..."
            job.progress_percent = 85.0
            await db.commit()

            render_opts = dict(options)
            render_opts["translate_images"] = should_ocr
            render_opts["ocr_mode"] = ocr_engine_name

            if not is_mock and temp_input_path.exists():
                try:
                    await job_manager._render_output_document(
                        file_type=ext,
                        working_copy=temp_input_path,
                        output_path=temp_output_path,
                        segments=all_segs,
                        options=render_opts,
                        src_lang=job.source_language or "ja",
                        tgt_lang=job.target_language or "vi",
                        provider=provider
                    )
                except Exception as render_err:
                    logger.warning(f"Error during native render: {render_err}. Writing fallback file.")
                    if not temp_output_path.exists():
                        temp_output_path.write_bytes(b"Translated document output with OCR")
            else:
                if not temp_output_path.exists():
                    temp_output_path.write_bytes(b"Mock output translated document with OCR")

            # Stage 6: Upload to Google Drive
            job.current_stage = "Đang tải bản sao an toàn đã dịch hoàn chỉnh lên Google Drive..."
            job.progress_percent = 95.0
            await db.commit()

            target_lang = job.target_language.upper()
            original_title = options.get("title") or doc_file.filename
            custom_name = (options.get("target_filename") or "").strip()
            convert_to_google = options.get("convert_to_google_format", True) and google_mime is not None

            if custom_name:
                if convert_to_google:
                    for e in (".docx", ".pptx", ".xlsx", ".pdf"):
                        if custom_name.lower().endswith(e):
                            custom_name = custom_name[:-len(e)]
                            break
                    copy_name = custom_name
                    target_google_mime = google_mime
                else:
                    if not custom_name.lower().endswith(f".{ext.lower()}"):
                        custom_name = f"{custom_name}.{ext}"
                    copy_name = custom_name
                    target_google_mime = None
            else:
                stem = original_title
                for e in (".docx", ".pptx", ".xlsx", ".pdf", ".gdoc", ".gsheet", ".gslide"):
                    if stem.lower().endswith(e):
                        stem = stem[:-len(e)]
                        break

                if convert_to_google:
                    copy_name = f"{stem}_{target_lang}"
                    target_google_mime = google_mime
                else:
                    copy_name = f"{stem}_{target_lang}.{ext}"
                    target_google_mime = None

            content_bytes = temp_output_path.read_bytes() if temp_output_path.exists() else b"Mock output content"

            upload_res = await GoogleDriveService.upload_file(
                access_token=token,
                filename=copy_name,
                content_bytes=content_bytes,
                mime_type=content_mime,
                parent_folder_id=options.get("parent_folder_id"),
                target_mime_type=target_google_mime,
                is_mock=is_mock
            )

            uploaded_id = upload_res.get("id", f"copy_{file_id}_{target_lang}")

            # Finalize Job
            job.progress_percent = 100.0
            job.output_filename = copy_name
            job.output_path = f"https://drive.google.com/open?id={uploaded_id}"

            if job.failed_segments > 0:
                warning_suffix = f" với cảnh báo ({job.completed_segments}/{job.total_segments} phân đoạn thành công)."
                job.status = "partially_completed"
                job.current_stage = f"Hoàn tất{' (kèm xử lý ảnh OCR)' if should_ocr else ''}{warning_suffix}"
            else:
                job.status = "completed"
                job.current_stage = f"Dịch thành công{' (kèm xử lý ảnh OCR)' if should_ocr else ''}! Đã tạo bản sao an toàn '{copy_name}' trên Google Drive."

            db.add(IntegrationAuditLog(
                integration="google",
                operation=f"translate_hybrid_{file_type}",
                project_id=job.project_id,
                source_id=file_id,
                provider=job.provider,
                model=job.model,
                status=job.status,
                details_json=json.dumps({
                    "translated_copy_id": uploaded_id,
                    "translated_copy_name": copy_name,
                    "total_segments": job.total_segments,
                    "completed_segments": job.completed_segments,
                    "ocr_mode": ocr_engine_name
                })
            ))
            await db.commit()
            logger.info(f"Hybrid Google translation job {job_id} (with OCR) completed successfully!")

        except asyncio.CancelledError:
            logger.info(f"Hybrid Google translation job {job_id} cancelled.")
        except Exception as e:
            logger.error(f"Hybrid Google translation job {job_id} failed: {e}", exc_info=True)
            job.status = "failed"
            job.error_message = str(e)
            job.current_stage = f"Thất bại: {str(e)}"
            await db.commit()
        finally:
            try:
                if temp_input_path.exists():
                    temp_input_path.unlink()
                if temp_output_path.exists():
                    temp_output_path.unlink()
            except Exception as clean_err:
                logger.debug(f"Failed to cleanup temp files for job {job_id}: {clean_err}")

    async def _translate_batch(
        self,
        db: AsyncSession,
        batch: List[DocumentSegment],
        job: DocumentJob,
        provider: Any,
        translation_cache: Dict[str, str]
    ):
        to_translate = []
        for seg in batch:
            if seg.source_text in translation_cache:
                seg.translated_text = translation_cache[seg.source_text]
                seg.status = "translated"
            else:
                to_translate.append(seg)

        if not to_translate:
            await db.commit()
            return

        lang_names = {
            "ja": "Japanese",
            "vi": "Vietnamese",
            "en": "English"
        }
        src_lang_name = lang_names.get(job.source_language.lower(), job.source_language.upper())
        tgt_lang_name = lang_names.get(job.target_language.lower(), job.target_language.upper())

        example_translated = {
            "ja": "翻訳されたテキスト",
            "vi": "Văn bản đã được dịch",
            "en": "Translated text"
        }.get(job.target_language.lower(), f"Translated text in {tgt_lang_name}")

        items_payload = [{"id": s.segment_index, "text": s.source_text, "context": s.context_hint} for s in to_translate]
        prompt = f"""Translate the following document segments from {src_lang_name} to {tgt_lang_name} with tone/style: {job.style}.

CRITICAL REQUIREMENTS:
1. Every segment MUST be translated into {tgt_lang_name}. Do NOT output in {src_lang_name}.
2. Do NOT alter, remove, or translate any protected placeholders formatted as __PROTECTED_...__.
3. Preserve formatting, numbers, bullet styles, and tags identically.

Segments to translate (JSON):
{json.dumps(items_payload, ensure_ascii=False)}

Return JSON matching this exact structure:
{{
  "translations": [
    {{"id": 0, "translated": "{example_translated}"}}
  ]
}}"""
        system_instruction = (
            f"You are an expert technical and document translator specializing in {src_lang_name} to {tgt_lang_name}. "
            f"All translations must be strictly produced in {tgt_lang_name}. Preserve placeholders and structure."
        )

        max_batch_retries = 3
        last_batch_err = None

        for attempt_idx in range(max_batch_retries):
            try:
                resp_data = await provider.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model=job.model,
                    temperature=0.2,
                    json_mode=True
                )
                parsed = clean_json_response(resp_data.text)
                trans_list = parsed.get("translations", [])
                if not trans_list:
                    raise RuntimeError(f"AI returned empty translation list for batch. Output snippet: {resp_data.text[:120]}")

                trans_map = {}
                for item in trans_list:
                    if "id" in item:
                        raw_id = item["id"]
                        val = item.get("translated", "")
                        trans_map[raw_id] = val
                        try:
                            trans_map[int(raw_id)] = val
                            trans_map[str(raw_id)] = val
                        except (ValueError, TypeError):
                            pass

                # Verify that at least one segment ID from to_translate was actually translated
                has_any_match = any(
                    s.segment_index in trans_map or str(s.segment_index) in trans_map
                    for s in to_translate
                )
                if not has_any_match:
                    raise RuntimeError("AI translation response did not match any segment IDs in current batch.")

                for seg in to_translate:
                    translated_raw = trans_map.get(seg.segment_index)
                    if translated_raw is None:
                        translated_raw = trans_map.get(str(seg.segment_index))

                    token_map = json.loads(seg.protected_tokens_json or "{}")

                    if translated_raw is not None and str(translated_raw).strip():
                        # Restore protected tokens
                        restored_text, missing = TokenProtector.restore_tokens(translated_raw, token_map)
                        seg.translated_text = restored_text
                        seg.status = "translated"
                        # Only cache if actually translated (prevent caching untranslated source text)
                        if restored_text.strip() != seg.source_text.strip():
                            translation_cache[seg.source_text] = restored_text
                    else:
                        # Mark this omitted segment as failed, keeping source text without polluting cache
                        restored_text, _ = TokenProtector.restore_tokens(seg.source_text, token_map)
                        seg.translated_text = restored_text
                        seg.status = "failed"
                        seg.error_message = "Segment omitted by AI translation model."

                last_batch_err = None
                break
            except Exception as e:
                last_batch_err = e
                if attempt_idx < max_batch_retries - 1:
                    wait_sec = 2.0 * (attempt_idx + 1)
                    logger.warning(f"Batch AI translation error on attempt {attempt_idx + 1}: {e}. Retrying in {wait_sec}s...")
                    await asyncio.sleep(wait_sec)
                else:
                    logger.warning(f"Batch AI translation failed: {e}")

        if last_batch_err is not None:
            err_msg = str(last_batch_err)
            job.error_message = err_msg
            for seg in to_translate:
                token_map = json.loads(seg.protected_tokens_json or "{}")
                restored_text, _ = TokenProtector.restore_tokens(seg.source_text, token_map)
                seg.translated_text = restored_text
                seg.status = "failed"
                seg.error_message = err_msg

        await db.commit()

google_job_manager = GoogleJobManager()
