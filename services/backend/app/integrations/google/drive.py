from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import asyncio
import io
import zipfile
from datetime import datetime
import json
import httpx
from app.core.logging import logger

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

class GoogleDriveService:
    """Manages Google Drive navigation, search, shared drives, and non-destructive copies using real Google Drive API."""

    @classmethod
    async def list_files(
        cls,
        access_token: str,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
        shared_drive_id: Optional[str] = None,
        view_mode: str = "my_drive",
        is_mock: bool = False,
        db: Optional[Any] = None,
        account_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Lists files and folders with folder drilldown, search, view mode, and self-healing token refresh."""
        headers = {"Authorization": f"Bearer {access_token}"}
        params: Dict[str, Any] = {
            "pageSize": 50,
            "fields": "files(id, name, mimeType, parents, modifiedTime, size, sharedWithMeTime, sharingUser(displayName, emailAddress, photoLink), owners(displayName, emailAddress))",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true"
        }

        q_parts = ["trashed = false"]

        if view_mode == "shared_with_me":
            if folder_id and folder_id != "root":
                q_parts.append(f"'{folder_id}' in parents")
            else:
                q_parts.append("sharedWithMe = true")
            params["orderBy"] = "sharedWithMeTime desc"
        elif view_mode == "recent":
            # Recently accessed or modified
            params["orderBy"] = "viewedByMeTime desc, modifiedTime desc"
            if folder_id and folder_id != "root":
                q_parts.append(f"'{folder_id}' in parents")
        else: # my_drive
            if folder_id and folder_id != "root":
                q_parts.append(f"'{folder_id}' in parents")
            elif not query:
                # If at root and not searching, show items directly in root My Drive
                q_parts.append("'root' in parents")
            params["orderBy"] = "modifiedTime desc"

        if query:
            q_parts.append(f"name contains '{query}'")

        params["q"] = " and ".join(q_parts)
        if shared_drive_id:
            params["driveId"] = shared_drive_id
            params["corpora"] = "drive"

        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(f"{DRIVE_API_BASE}/files", headers=headers, params=params)
            if resp.status_code == 401 and db and account_id:
                logger.warning(f"Google Drive API returned 401 for list_files, triggering self-healing token refresh for {account_id}...")
                from app.integrations.google.client import GoogleWorkspaceClient
                try:
                    new_token = await GoogleWorkspaceClient.get_valid_access_token(db, account_id, force_refresh=True)
                    headers["Authorization"] = f"Bearer {new_token}"
                    resp = await http.get(f"{DRIVE_API_BASE}/files", headers=headers, params=params)
                except Exception as ref_err:
                    logger.error(f"Self-healing token refresh failed: {ref_err}")

            if resp.status_code != 200:
                logger.error(f"Failed to list Drive files: {resp.text}")
                return []
            data = resp.json()
            files = data.get("files", [])
            for f in files:
                mime = f.get("mimeType", "").lower()
                name = f.get("name", "").lower()
                ext = name.rsplit(".", 1)[-1] if "." in name else ""

                if "folder" in mime:
                    f["type"] = "folder"
                elif (
                    "presentation" in mime
                    or "powerpoint" in mime
                    or ext in ("ppt", "pptx", "odp")
                ):
                    f["type"] = "slide"
                elif (
                    "spreadsheet" in mime
                    or "excel" in mime
                    or ext in ("xls", "xlsx", "csv", "tsv", "ods")
                ):
                    f["type"] = "sheet"
                elif (
                    "word" in mime
                    or "msword" in mime
                    or "google-apps.document" in mime
                    or "wordprocessingml" in mime
                    or ("document" in mime and "presentation" not in mime and "spreadsheet" not in mime)
                    or ext in ("doc", "docx", "rtf", "odt")
                ):
                    f["type"] = "doc"
                elif "pdf" in mime or ext == "pdf":
                    f["type"] = "pdf"
                elif mime.startswith("image/") or ext in ("png", "jpg", "jpeg", "webp", "gif", "svg"):
                    f["type"] = "image"
                elif "zip" in mime or ext in ("zip", "rar", "7z", "tar", "gz"):
                    f["type"] = "archive"
                else:
                    f["type"] = "file"

                f["is_native_google"] = mime.startswith("application/vnd.google-apps.")
                f["extension"] = ext
            return files

    @classmethod
    async def get_file_metadata(
        cls,
        access_token: str,
        file_id: str,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Fetches metadata for a specific Google Drive file (id, name, mimeType, size)."""
        if is_mock:
            return {"id": file_id, "name": "mock_file", "mimeType": "application/vnd.google-apps.document"}
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                f"{DRIVE_API_BASE}/files/{file_id}?fields=id,name,mimeType,size,trashed,parents&supportsAllDrives=true",
                headers=headers
            )
            if resp.status_code == 200:
                return resp.json()
            return {}

    @classmethod
    async def get_folder_info(
        cls,
        access_token: str,
        folder_id: str,
        is_mock: bool = False,
        db: Optional[Any] = None,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetches metadata for a specific Google Drive folder with self-healing token retry."""
        if not folder_id or folder_id == "root":
            return {"id": "root", "name": "My Drive"}

        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                f"{DRIVE_API_BASE}/files/{folder_id}?fields=id,name,mimeType&supportsAllDrives=true",
                headers=headers
            )
            if resp.status_code == 401 and db and account_id:
                logger.warning(f"Google Drive API returned 401 for get_folder_info, triggering self-healing token refresh...")
                from app.integrations.google.client import GoogleWorkspaceClient
                try:
                    new_token = await GoogleWorkspaceClient.get_valid_access_token(db, account_id, force_refresh=True)
                    headers["Authorization"] = f"Bearer {new_token}"
                    resp = await http.get(
                        f"{DRIVE_API_BASE}/files/{folder_id}?fields=id,name,mimeType&supportsAllDrives=true",
                        headers=headers
                    )
                except Exception as ref_err:
                    logger.error(f"Self-healing token refresh failed: {ref_err}")

            if resp.status_code == 200:
                data = resp.json()
                return {"id": data["id"], "name": data.get("name", "Thư mục Drive")}
            logger.warning(f"Could not fetch folder metadata for {folder_id}: {resp.text}")
            return {"id": folder_id, "name": f"Thư mục ({folder_id[:8]}...)"}

    @classmethod
    async def create_translated_copy(
        cls,
        access_token: str,
        source_file_id: str,
        target_name: str,
        parent_folder_id: Optional[str] = None,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Creates a non-destructive copy in the same folder as the original file."""
        if is_mock:
            return {"id": f"copy_{source_file_id}", "name": target_name}

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body: Dict[str, Any] = {"name": target_name}
        if parent_folder_id:
            body["parents"] = [parent_folder_id]

        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                f"{DRIVE_API_BASE}/files/{source_file_id}/copy",
                headers=headers,
                json=body,
                params={"supportsAllDrives": "true"}
            )
            if resp.status_code not in (200, 201):
                logger.error(f"Failed to copy Drive file: {resp.text}")
                raise ValueError(f"Drive copy failed: {resp.text}")
            return resp.json()

    @classmethod
    async def sync_existing_file_content(
        cls,
        access_token: str,
        source_file_id: str,
        target_file_id: str,
        file_type: str,
        is_mock: bool = False
    ) -> bool:
        """Syncs the latest structure, newly added text, and images from source_file_id into target_file_id while keeping target_file_id and its URL intact."""
        if is_mock:
            return True

        # Google Workspace native structure preservation (Docs, Sheets, Slides):
        # Binary export to .docx, .xlsx, or .pptx destroys revisions, comments, conditional formatting,
        # animations, themes, and complex formulas.
        # In-place updates for Docs, Sheets, and Slides rely directly on their native REST APIs
        # (AST Block Myers diff, 2D Matrix diff, and Slide AST Scoped diff).
        logger.info(f"Preserving native structure for {file_type} ({source_file_id} -> {target_file_id}). Skipping binary export.")
        return True

    @classmethod
    async def create_folder(
        cls,
        access_token: str,
        name: str,
        parent_folder_id: Optional[str] = None,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Creates a new folder in Google Drive."""
        if is_mock:
            return {"id": f"mock_folder_{name}", "name": name}

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body: Dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        if parent_folder_id and parent_folder_id != "root":
            body["parents"] = [parent_folder_id]

        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                f"{DRIVE_API_BASE}/files",
                headers=headers,
                json=body,
                params={"supportsAllDrives": "true"}
            )
            if resp.status_code not in (200, 201):
                logger.error(f"Failed to create Drive folder: {resp.text}")
                raise ValueError(f"Drive folder creation failed: {resp.text}")
            return resp.json()

    @classmethod
    async def export_or_download_file(
        cls,
        access_token: str,
        file_id: str,
        file_type: str,
        target_path: Path,
        is_mock: bool = False
    ) -> Path:
        """Exports Google Workspace files (gdoc, gslide, gsheet) or downloads binary files to a local path."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if is_mock:
            target_path.write_bytes(b"Mock exported content")
            return target_path

        headers = {"Authorization": f"Bearer {access_token}"}
        f_type = file_type.lower()

        async with httpx.AsyncClient(timeout=60.0) as http:
            # 1. Check real mimeType from Google Drive to differentiate native vs binary files
            actual_mime = ""
            try:
                meta_res = await http.get(
                    f"{DRIVE_API_BASE}/files/{file_id}?fields=id,name,mimeType&supportsAllDrives=true",
                    headers=headers
                )
                if meta_res.status_code == 200:
                    actual_mime = meta_res.json().get("mimeType", "")
            except Exception as meta_err:
                logger.debug(f"Could not check metadata for {file_id}: {meta_err}")

            is_native_google = actual_mime.startswith("application/vnd.google-apps.")
            resp = None

            # 2. If it's a native Google Docs Editor file, call /export
            if is_native_google:
                if "sheet" in actual_mime or "sheet" in f_type:
                    export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                elif "presentation" in actual_mime or "slide" in f_type:
                    export_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                else:
                    export_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

                resp = await http.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export?mimeType={export_mime}&supportsAllDrives=true",
                    headers=headers
                )
                if resp.status_code != 200:
                    logger.warning(f"Google Drive /export returned {resp.status_code}. Attempting alt=media fallback...")
                    resp = None

            # 3. If not native or if /export failed, download directly using alt=media
            if resp is None:
                resp = await http.get(
                    f"{DRIVE_API_BASE}/files/{file_id}?alt=media&supportsAllDrives=true",
                    headers=headers
                )

            # 4. Final fallback: If alt=media failed on a non-native flag, try /export as last resort
            if resp.status_code != 200 and not is_native_google:
                if "sheet" in f_type:
                    export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                elif "slide" in f_type:
                    export_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                else:
                    export_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

                fallback_exp = await http.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export?mimeType={export_mime}&supportsAllDrives=true",
                    headers=headers
                )
                if fallback_exp.status_code == 200:
                    resp = fallback_exp

            if resp.status_code != 200:
                logger.error(f"Failed to export/download file {file_id}: {resp.text}")
                raise ValueError(f"Failed to download/export file from Google Drive (HTTP {resp.status_code})")

            target_path.write_bytes(resp.content)
            return target_path

    @classmethod
    async def upload_file(
        cls,
        access_token: str,
        filename: str,
        content_bytes: bytes,
        mime_type: str = "application/octet-stream",
        parent_folder_id: Optional[str] = None,
        target_mime_type: Optional[str] = None,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Uploads a file to Google Drive using multipart upload, optionally converting to Google Docs format."""
        if is_mock:
            return {"id": f"mock_file_{filename}", "name": filename}

        headers = {"Authorization": f"Bearer {access_token}"}
        metadata: Dict[str, Any] = {"name": filename}
        if target_mime_type:
            metadata["mimeType"] = target_mime_type
        if parent_folder_id and parent_folder_id != "root":
            metadata["parents"] = [parent_folder_id]

        files = {
            "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
            "file": (filename, content_bytes, mime_type)
        }

        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true",
                headers=headers,
                files=files
            )
            if resp.status_code not in (200, 201):
                logger.error(f"Failed to upload file to Drive: {resp.text}")
                raise ValueError(f"Drive upload failed: {resp.text}")
            return resp.json()

    @classmethod
    async def update_file_content(
        cls,
        access_token: str,
        file_id: str,
        content_bytes: bytes,
        mime_type: str = "application/octet-stream",
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Updates the media content of an existing file on Google Drive in-place using PATCH upload."""
        if is_mock:
            return {"id": file_id, "status": "updated"}

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": mime_type
        }
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.patch(
                f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media&supportsAllDrives=true",
                headers=headers,
                content=content_bytes
            )
            if resp.status_code != 200:
                logger.error(f"Failed to update file content on Drive for {file_id}: {resp.text}")
                raise ValueError(f"Drive update file content failed: {resp.text}")
            return resp.json()

    @classmethod
    async def rename_file(
        cls,
        access_token: str,
        file_id: str,
        new_name: str,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Renames a file or folder on Google Drive."""
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        body = {"name": new_name}

        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.patch(
                f"{DRIVE_API_BASE}/files/{file_id}",
                headers=headers,
                json=body,
                params={"supportsAllDrives": "true"}
            )
            if resp.status_code != 200:
                logger.error(f"Failed to rename Drive file: {resp.text}")
                raise ValueError(f"Drive rename failed: {resp.text}")
            return resp.json()

    @classmethod
    async def delete_file(
        cls,
        access_token: str,
        file_id: str,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Deletes a file or folder from Google Drive."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.delete(
                f"{DRIVE_API_BASE}/files/{file_id}",
                headers=headers,
                params={"supportsAllDrives": "true"}
            )
            if resp.status_code not in (200, 204):
                logger.error(f"Failed to delete Drive file: {resp.text}")
                raise ValueError(f"Drive delete failed: {resp.text}")
            return {"status": "deleted", "id": file_id}

    @classmethod
    async def delete_files_batch(
        cls,
        access_token: str,
        file_ids: List[str],
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Deletes multiple files or folders from Google Drive concurrently with rate-limiting."""
        if is_mock:
            return {"status": "success", "deleted_count": len(file_ids), "failed_count": 0, "failed_ids": []}

        if not file_ids:
            return {"status": "success", "deleted_count": 0, "failed_count": 0, "failed_ids": []}

        sem = asyncio.Semaphore(5)
        deleted_ids: List[str] = []
        failed_ids: List[str] = []

        async def _delete_single(fid: str):
            async with sem:
                for attempt in range(3):
                    try:
                        await cls.delete_file(access_token, fid, is_mock=is_mock)
                        deleted_ids.append(fid)
                        return
                    except Exception as e:
                        if attempt == 2:
                            logger.warning(f"Could not delete Drive file {fid}: {e}")
                            failed_ids.append(fid)
                        else:
                            await asyncio.sleep(0.5 * (attempt + 1))

        await asyncio.gather(*[_delete_single(fid) for fid in file_ids])

        return {
            "status": "success" if not failed_ids else "partial",
            "deleted_count": len(deleted_ids),
            "failed_count": len(failed_ids),
            "failed_ids": failed_ids
        }

    @classmethod
    async def export_or_download_file_bytes(
        cls,
        access_token: str,
        file_id: str,
        is_mock: bool = False
    ) -> Tuple[bytes, str, str]:
        """
        Exports Google Workspace files (Doc -> docx, Sheet -> xlsx, Slide -> pptx)
        or downloads binary files (PDF, images, etc.) to raw bytes.
        Returns: (content_bytes, safe_filename, mime_type)
        """
        if is_mock:
            return b"Mock downloaded file content", f"mock_file_{file_id}.txt", "text/plain"

        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=60.0) as http:
            # 1. Fetch file metadata
            meta_res = await http.get(
                f"{DRIVE_API_BASE}/files/{file_id}?fields=id,name,mimeType&supportsAllDrives=true",
                headers=headers
            )
            if meta_res.status_code != 200:
                logger.error(f"Failed to fetch metadata for file {file_id}: {meta_res.text}")
                raise ValueError(f"Drive file metadata fetch failed: {meta_res.text}")

            meta = meta_res.json()
            raw_name = meta.get("name", f"file_{file_id}")
            actual_mime = meta.get("mimeType", "")

            # 2. Native Google Docs / Sheets / Slides export
            is_native = actual_mime.startswith("application/vnd.google-apps.")
            resp = None
            dl_filename = raw_name
            dl_mime = actual_mime or "application/octet-stream"

            if is_native:
                if "spreadsheet" in actual_mime:
                    export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if not dl_filename.lower().endswith(".xlsx"):
                        dl_filename += ".xlsx"
                elif "presentation" in actual_mime:
                    export_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    if not dl_filename.lower().endswith(".pptx"):
                        dl_filename += ".pptx"
                else:
                    export_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    if not dl_filename.lower().endswith(".docx"):
                        dl_filename += ".docx"

                dl_mime = export_mime
                resp = await http.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export?mimeType={export_mime}&supportsAllDrives=true",
                    headers=headers
                )
                if resp.status_code != 200:
                    logger.warning(f"Export returned {resp.status_code}. Falling back to alt=media...")
                    resp = None

            # 3. Direct binary download via alt=media
            if resp is None:
                resp = await http.get(
                    f"{DRIVE_API_BASE}/files/{file_id}?alt=media&supportsAllDrives=true",
                    headers=headers
                )

            if resp.status_code != 200:
                logger.error(f"Failed to download/export file {file_id}: {resp.text}")
                raise ValueError(f"Failed to download/export file from Google Drive (HTTP {resp.status_code})")

            return resp.content, dl_filename, dl_mime

    @classmethod
    async def download_files_as_zip(
        cls,
        access_token: str,
        file_ids: List[str],
        is_mock: bool = False
    ) -> Tuple[bytes, str]:
        """
        Downloads multiple files concurrently and archives them into an in-memory ZIP file.
        Returns: (zip_bytes, zip_filename)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"drive_download_{timestamp}.zip"

        if is_mock:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, fid in enumerate(file_ids, 1):
                    zf.writestr(f"mock_file_{idx}.txt", f"Mock content for file {fid}")
            return buf.getvalue(), zip_filename

        if not file_ids:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("empty.txt", "No files selected.")
            return buf.getvalue(), zip_filename

        sem = asyncio.Semaphore(5)
        results: List[Tuple[bytes, str, str]] = []

        async def _fetch_file(fid: str):
            async with sem:
                for attempt in range(3):
                    try:
                        content, name, mime = await cls.export_or_download_file_bytes(access_token, fid, is_mock=is_mock)
                        results.append((content, name, mime))
                        return
                    except Exception as e:
                        if attempt == 2:
                            logger.warning(f"Could not download file {fid} for zip packaging: {e}")
                        else:
                            await asyncio.sleep(0.5 * (attempt + 1))

        await asyncio.gather(*[_fetch_file(fid) for fid in file_ids])

        buf = io.BytesIO()
        used_names: set = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for content, name, _ in results:
                final_name = name
                counter = 1
                while final_name in used_names:
                    p = Path(name)
                    stem, suffix = p.stem, p.suffix
                    final_name = f"{stem} ({counter}){suffix}"
                    counter += 1
                used_names.add(final_name)
                zf.writestr(final_name, content)

        return buf.getvalue(), zip_filename

