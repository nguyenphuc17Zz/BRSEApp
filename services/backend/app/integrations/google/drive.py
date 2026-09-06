from typing import Dict, List, Any, Optional
from pathlib import Path
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
                f"{DRIVE_API_BASE}/files/{file_id}?fields=id,name,mimeType,size,trashed&supportsAllDrives=true",
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

        headers = {"Authorization": f"Bearer {access_token}"}
        f_type = (file_type or "").lower()

        if "sheet" in f_type:
            export_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            sync_filename = "sync.xlsx"
        elif "slide" in f_type or "presentation" in f_type:
            export_mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            sync_filename = "sync.pptx"
        else:
            # Google Docs native multi-tab preservation:
            # Microsoft Word (.docx) has no concept of tabs. When Google Docs exports a multi-tab document to .docx,
            # Google Drive's export engine flattens all tabs into one and injects tab titles into the body text.
            # Re-uploading that DOCX destroys the multi-tab layout and permanently injects tab names into the document body.
            # Therefore, Google Docs in-place updates must skip DOCX conversion and rely on native Docs REST API.
            logger.info(f"Preserving native Google Doc multi-tab structure for {source_file_id} -> {target_file_id}. Skipping DOCX export.")
            return True

        async with httpx.AsyncClient(timeout=60.0) as http:
            exp_res = await http.get(
                f"{DRIVE_API_BASE}/files/{source_file_id}/export?mimeType={export_mime}&supportsAllDrives=true",
                headers=headers
            )
            if exp_res.status_code != 200:
                logger.warning(f"Could not export source file {source_file_id} for in-place sync: HTTP {exp_res.status_code}")
                return False

            file_bytes = exp_res.content
            files = {
                "data": ("metadata", json.dumps({}), "application/json; charset=UTF-8"),
                "file": (sync_filename, file_bytes, export_mime)
            }
            up_res = await http.patch(
                f"https://www.googleapis.com/upload/drive/v3/files/{target_file_id}?uploadType=multipart&supportsAllDrives=true",
                headers={"Authorization": f"Bearer {access_token}"},
                files=files
            )
            if up_res.status_code == 200:
                logger.info(f"Successfully synced fresh layout and content from {source_file_id} to existing file {target_file_id}.")
                return True
            else:
                logger.warning(f"Drive API failed to patch target file {target_file_id}: HTTP {up_res.status_code} - {up_res.text[:150]}")
                return False

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
