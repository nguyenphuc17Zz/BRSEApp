import datetime
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body, UploadFile, File, Form
from fastapi.responses import RedirectResponse
import httpx
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings, BASE_DIR
from app.core.database import get_db
from app.core.logging import logger
from app.core.security import encrypt_credential, decrypt_credential
from app.documents.models import DocumentFile, DocumentJob, DocumentSegment, DocumentIssue
from app.documents.segmenter import TokenProtector
from app.integrations.models import IntegrationAccount, IntegrationAuditLog
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.drive import GoogleDriveService
from app.integrations.google.docs import GoogleDocsService
from app.integrations.google.sheets import GoogleSheetsService
from app.integrations.google.slides import GoogleSlidesService
from app.integrations.google.google_jobs import google_job_manager
from app.engine.pipeline import translation_pipeline
from app.providers.registry import provider_registry
from app.schemas.schemas import TranslationRequest

router = APIRouter(prefix="/google", tags=["Google Workspace"])

class GoogleConnectRequest(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_code: Optional[str] = None
    is_mock: bool = False
    account_name: str = "Google Workspace"

class GoogleTranslationStartRequest(BaseModel):
    file_id: str
    file_type: str # doc, sheet, slide, gdoc, gsheet, gslide
    title: str = "Document"
    source_language: str = "ja"
    target_language: str = "vi"
    project_id: Optional[str] = None
    style: str = "Business"
    provider: str = "gemini"
    model: Optional[str] = "gemini-3.7-flash"
    selected_sheets: Optional[List[str]] = None
    translate_notes: bool = True
    parent_folder_id: Optional[str] = None
    account_id: Optional[str] = None
    translate_images: bool = False
    ocr_mode: str = "paddleocr"
    convert_to_google_format: bool = True
    target_filename: Optional[str] = None

class GoogleDocTranslateRequest(BaseModel):
    project_id: Optional[str] = None
    target_language: str = "vi"
    style: str = "Formal"
    provider: str = "gemini"
    model: Optional[str] = None
    account_id: Optional[str] = None

class GoogleSheetTranslateRequest(BaseModel):
    project_id: Optional[str] = None
    target_language: str = "vi"
    selected_sheets: Optional[List[str]] = None
    selected_range: Optional[str] = None
    style: str = "Technical"
    provider: str = "gemini"
    model: Optional[str] = None
    account_id: Optional[str] = None

class DriveCreateFolderRequest(BaseModel):
    name: str
    parent_folder_id: Optional[str] = None
    account_id: Optional[str] = None

class DriveRenameRequest(BaseModel):
    new_name: str
    account_id: Optional[str] = None

async def get_target_google_account(db: AsyncSession, account_id: Optional[str] = None) -> IntegrationAccount:
    """Resolves the target Google Workspace account (by explicit ID, active flag, or latest record)."""
    if account_id:
        acc = (await db.execute(
            select(IntegrationAccount).where(
                IntegrationAccount.provider == "google",
                IntegrationAccount.id == account_id
            )
        )).scalar_one_or_none()
        if acc:
            return acc

    # Default to active account
    acc = (await db.execute(
        select(IntegrationAccount).where(
            IntegrationAccount.provider == "google",
            IntegrationAccount.is_active == True
        )
    )).scalars().first()

    if not acc:
        acc = (await db.execute(
            select(IntegrationAccount).where(
                IntegrationAccount.provider == "google"
            ).order_by(IntegrationAccount.created_at.desc())
        )).scalars().first()

    if not acc:
        raise HTTPException(status_code=400, detail="Google Workspace chưa được kết nối tài khoản nào.")

    return acc

def update_env_file(key_values: Dict[str, str]):
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in key_values:
                new_lines.append(f"{k}={key_values[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)
    
    for k, v in key_values.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")
            
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def parse_google_credentials_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Nội dung file JSON không hợp lệ: {str(e)}")
    elif isinstance(raw, dict):
        data = raw
    else:
        raise HTTPException(status_code=400, detail="Định dạng payload không hợp lệ.")

    conf = data.get("web") or data.get("installed") or data
    client_id = conf.get("client_id", "").strip()
    client_secret = conf.get("client_secret", "").strip()
    project_id = conf.get("project_id", "").strip()
    redirect_uris = conf.get("redirect_uris", [])

    if not client_id:
        raise HTTPException(status_code=400, detail="Vui lòng điền 'Client ID' (lấy từ Google Cloud Console).")
    if not client_secret:
        raise HTTPException(status_code=400, detail="Vui lòng điền 'Client Secret' (lấy từ Google Cloud Console).")

    if not project_id and "-" in client_id:
        project_id = "AutomationTranslate"

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "project_id": project_id or "AutomationTranslate",
        "redirect_uris": redirect_uris
    }

@router.get("/config")
async def get_google_config():
    client_id = (settings.GOOGLE_CLIENT_ID or "").strip()
    client_secret = (settings.GOOGLE_CLIENT_SECRET or "").strip()
    project_id = (settings.GOOGLE_PROJECT_ID or "").strip()
    is_configured = bool(client_id and client_secret)

    masked_id = ""
    if is_configured and client_id:
        if len(client_id) > 30:
            masked_id = f"{client_id[:10]}...{client_id[-28:]}"
        else:
            masked_id = "***"
            
    return {
        "is_configured": is_configured,
        "client_id_masked": masked_id,
        "project_id": project_id if is_configured else "",
        "redirect_uri": "http://127.0.0.1:8000/api/integrations/google/callback"
    }

@router.post("/config/upload-credentials")
async def upload_google_credentials(payload: Dict[str, Any] = Body(...)):
    parsed = parse_google_credentials_payload(payload)
    client_id = parsed["client_id"]
    client_secret = parsed["client_secret"]
    project_id = parsed["project_id"]
    redirect_uris = parsed["redirect_uris"]

    expected_redirect = "http://127.0.0.1:8000/api/integrations/google/callback"
    redirect_warning = None
    if redirect_uris and expected_redirect not in redirect_uris:
        redirect_warning = (
            f"Lưu ý: File credentials của bạn chưa có Authorized redirect URI '{expected_redirect}'. "
            "Hãy đảm bảo thêm URI này trên Google Cloud Console nếu Google báo redirect_uri_mismatch khi đăng nhập."
        )

    settings.GOOGLE_CLIENT_ID = client_id
    settings.GOOGLE_CLIENT_SECRET = client_secret
    if project_id:
        settings.GOOGLE_PROJECT_ID = project_id

    env_updates = {
        "GOOGLE_CLIENT_ID": client_id,
        "GOOGLE_CLIENT_SECRET": client_secret
    }
    if project_id:
        env_updates["GOOGLE_PROJECT_ID"] = project_id
    update_env_file(env_updates)

    logger.info(f"Updated Google OAuth credentials from uploaded JSON: project_id={project_id}")

    return {
        "success": True,
        "message": "Đã tự động nạp Client ID & Secret thành công!",
        "client_id_masked": f"{client_id[:10]}...{client_id[-28:]}" if len(client_id) > 30 else "***",
        "project_id": project_id,
        "redirect_warning": redirect_warning
    }

@router.get("/login-url")
async def get_login_url():
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=400, detail="Google OAuth chưa được cấu hình Client ID. Vui lòng tải lên file credentials.json trước.")
    
    redirect_uri = "http://127.0.0.1:8000/api/integrations/google/callback"
    auth_url = GoogleWorkspaceClient.get_auth_url(client_id, redirect_uri)
    return {"auth_url": auth_url}

@router.get("/callback")
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    if error:
        logger.error(f"Google OAuth callback error: {error}")
        return RedirectResponse(f"http://localhost:5173/integrations?google_error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        return RedirectResponse("http://localhost:5173/integrations?google_error=missing_credentials")

    redirect_uri = "http://127.0.0.1:8000/api/integrations/google/callback"
    try:
        tokens = await GoogleWorkspaceClient.exchange_code_for_tokens(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri
        )

        profile = await GoogleWorkspaceClient.fetch_user_profile(tokens["access_token"])
        user_email = profile["email"]
        user_name = profile["name"]

        # Check if account with this email already exists
        existing_acc = (await db.execute(
            select(IntegrationAccount).where(
                IntegrationAccount.provider == "google",
                IntegrationAccount.email == user_email
            )
        )).scalars().first()

        # Mark all other accounts inactive so the newly authenticated account becomes active
        other_accs = (await db.execute(
            select(IntegrationAccount).where(IntegrationAccount.provider == "google")
        )).scalars().all()
        for other in other_accs:
            other.is_active = False

        if existing_acc:
            existing_acc.encrypted_access_token = encrypt_credential(tokens["access_token"])
            if tokens.get("refresh_token"):
                existing_acc.encrypted_refresh_token = encrypt_credential(tokens["refresh_token"])
            existing_acc.scopes_json = json.dumps(tokens.get("scope", "").split(" "))
            existing_acc.is_active = True
            existing_acc.is_mock = False
            existing_acc.token_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=tokens.get("expires_in", 3600))
            existing_acc.last_sync_at = datetime.datetime.utcnow()
            account = existing_acc
        else:
            account = IntegrationAccount(
                provider="google",
                account_name=f"Google Drive ({user_email})",
                email=user_email,
                encrypted_access_token=encrypt_credential(tokens["access_token"]),
                encrypted_refresh_token=encrypt_credential(tokens.get("refresh_token", "")),
                scopes_json=json.dumps(tokens.get("scope", "").split(" ")),
                is_active=True,
                is_mock=False,
                token_expiry=datetime.datetime.utcnow() + datetime.timedelta(seconds=tokens.get("expires_in", 3600)),
                last_sync_at=datetime.datetime.utcnow()
            )
            db.add(account)

        await db.commit()

        logger.info(f"Google Workspace OAuth connected successfully: {user_email}")
        return RedirectResponse("http://localhost:5173/integrations?google_connected=true")
    except Exception as e:
        logger.error(f"Error handling Google OAuth callback: {e}")
        return RedirectResponse(f"http://localhost:5173/integrations?google_error={str(e)}")

@router.get("/auth-url")
async def get_google_auth_url(client_id: str, redirect_uri: str):
    return {"auth_url": GoogleWorkspaceClient.get_auth_url(client_id, redirect_uri)}

@router.post("/connect")
async def connect_google(req: GoogleConnectRequest, db: AsyncSession = Depends(get_db)):
    """Connects Google Workspace (Live OAuth)."""
    if not req.auth_code:
        raise HTTPException(
            status_code=400,
            detail="Thiếu mã authorization code. Vui lòng bấm 'Đăng Nhập Google (Tài Khoản Thật)' để xác thực."
        )

    client_id = req.client_id or settings.GOOGLE_CLIENT_ID
    client_secret = req.client_secret or settings.GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình Google Client ID hoặc Client Secret. Vui lòng tải file credentials.json lên trước."
        )

    tokens = await GoogleWorkspaceClient.exchange_code_for_tokens(
        code=req.auth_code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8000/api/integrations/google/callback"
    )

    profile = await GoogleWorkspaceClient.fetch_user_profile(tokens["access_token"])
    user_email = profile["email"]
    user_name = profile["name"]

    existing_acc = (await db.execute(
        select(IntegrationAccount).where(
            IntegrationAccount.provider == "google",
            IntegrationAccount.email == user_email
        )
    )).scalars().first()

    other_accs = (await db.execute(
        select(IntegrationAccount).where(IntegrationAccount.provider == "google")
    )).scalars().all()
    for other in other_accs:
        other.is_active = False

    if existing_acc:
        existing_acc.encrypted_access_token = encrypt_credential(tokens["access_token"])
        if tokens.get("refresh_token"):
            existing_acc.encrypted_refresh_token = encrypt_credential(tokens["refresh_token"])
        existing_acc.scopes_json = json.dumps(tokens.get("scope", "").split(" "))
        existing_acc.is_active = True
        existing_acc.is_mock = False
        existing_acc.token_expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=tokens.get("expires_in", 3600))
        existing_acc.last_sync_at = datetime.datetime.utcnow()
        account = existing_acc
    else:
        account = IntegrationAccount(
            provider="google",
            account_name=req.account_name or f"Google Drive ({user_email})",
            email=user_email,
            encrypted_access_token=encrypt_credential(tokens["access_token"]),
            encrypted_refresh_token=encrypt_credential(tokens.get("refresh_token", "")),
            scopes_json=json.dumps(tokens.get("scope", "").split(" ")),
            is_active=True,
            is_mock=False,
            token_expiry=datetime.datetime.utcnow() + datetime.timedelta(seconds=tokens.get("expires_in", 3600)),
            last_sync_at=datetime.datetime.utcnow()
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)

    return {
        "status": "connected",
        "account_id": account.id,
        "account_name": account.account_name,
        "email": account.email,
        "is_mock": False
    }

@router.get("/accounts")
async def list_google_accounts(db: AsyncSession = Depends(get_db)):
    """Lists all connected Google Workspace accounts. Auto-heals placeholder emails to real Gmail."""
    stmt = (
        select(IntegrationAccount)
        .where(IntegrationAccount.provider == "google")
        .order_by(IntegrationAccount.is_active.desc(), IntegrationAccount.created_at.desc())
    )
    accounts = (await db.execute(stmt)).scalars().all()

    # Auto-heal: If any account has placeholder email, try to fetch real email in background
    needs_commit = False
    for a in accounts:
        if not a.email or a.email.startswith("connected."):
            try:
                token = await GoogleWorkspaceClient.get_valid_access_token(db, a.id)
                profile = await GoogleWorkspaceClient.fetch_user_profile(token)
                if profile.get("email") and not profile["email"].startswith("connected."):
                    a.email = profile["email"]
                    a.account_name = f"Google Drive ({profile['email']})"
                    a.last_sync_at = datetime.datetime.utcnow()
                    needs_commit = True
            except Exception as e:
                logger.debug(f"Auto-heal email sync skipped for {a.id}: {e}")

    if needs_commit:
        await db.commit()

    return [
        {
            "id": a.id,
            "email": a.email,
            "account_name": a.account_name,
            "is_active": a.is_active,
            "is_mock": a.is_mock,
            "last_sync": a.last_sync_at.isoformat() if a.last_sync_at else None,
        }
        for a in accounts
    ]

@router.post("/accounts/sync-profile")
async def sync_google_profiles(account_id: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    """Refreshes and syncs the real email and display name for Google accounts via Drive API."""
    if account_id:
        accs = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.id == account_id))).scalars().all()
    else:
        accs = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google"))).scalars().all()

    updated = []
    for acc in accs:
        try:
            token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
            profile = await GoogleWorkspaceClient.fetch_user_profile(token)
            if profile.get("email") and not profile["email"].startswith("connected."):
                acc.email = profile["email"]
                acc.account_name = f"Google Drive ({profile['email']})"
                acc.last_sync_at = datetime.datetime.utcnow()
                updated.append({"id": acc.id, "email": acc.email, "name": acc.account_name})
        except Exception as e:
            logger.warning(f"Failed to sync profile for Google account {acc.id}: {e}")

    if updated:
        await db.commit()

    return {"status": "synced", "updated_count": len(updated), "accounts": updated}

@router.post("/accounts/{account_id}/activate")
async def activate_google_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """Switches the active Google Workspace account."""
    accounts = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google"))).scalars().all()
    target = None
    for acc in accounts:
        if acc.id == account_id:
            acc.is_active = True
            target = acc
        else:
            acc.is_active = False

    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản Google với ID này.")

    await db.commit()
    return {"status": "activated", "account_id": target.id, "email": target.email}

@router.delete("/accounts/{account_id}")
async def remove_google_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """Disconnects a specific Google Workspace account."""
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.id == account_id))).scalar_one_or_none()
    if not acc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản Google với ID này.")

    was_active = acc.is_active
    await db.delete(acc)
    await db.commit()

    if was_active:
        next_acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google").order_by(IntegrationAccount.created_at.desc()))).scalars().first()
        if next_acc:
            next_acc.is_active = True
            await db.commit()

    return {"status": "removed", "account_id": account_id}

@router.post("/disconnect")
async def disconnect_google(account_id: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    if account_id:
        acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.id == account_id))).scalar_one_or_none()
        if acc:
            was_active = acc.is_active
            await db.delete(acc)
            await db.commit()
            if was_active:
                next_acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google").order_by(IntegrationAccount.created_at.desc()))).scalars().first()
                if next_acc:
                    next_acc.is_active = True
                    await db.commit()
            return {"status": "disconnected", "account_id": account_id}
        return {"status": "not_found"}

    existing = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google"))).scalars().all()
    for acc in existing:
        await db.delete(acc)
    await db.commit()
    return {"status": "disconnected"}

@router.get("/drive")
async def list_drive_files(
    folder_id: Optional[str] = None,
    query: Optional[str] = None,
    account_id: Optional[str] = Query(None),
    view_mode: str = Query("my_drive", description="my_drive, shared_with_me, recent"),
    db: AsyncSession = Depends(get_db)
):
    """Lists files and folders from Google Drive for the specified or active account with view_mode."""
    acc = await get_target_google_account(db, account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    files = await GoogleDriveService.list_files(
        token,
        folder_id=folder_id,
        query=query,
        view_mode=view_mode,
        is_mock=acc.is_mock
    )
    
    current_folder = None
    if folder_id:
        current_folder = await GoogleDriveService.get_folder_info(token, folder_id, is_mock=acc.is_mock)

    return {
        "files": files,
        "current_folder": current_folder,
        "account_id": acc.id,
        "account_email": acc.email,
        "view_mode": view_mode
    }

@router.get("/drive/folders/{folder_id}")
async def get_drive_folder_info(
    folder_id: str,
    account_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves Google Drive folder metadata."""
    acc = await get_target_google_account(db, account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    info = await GoogleDriveService.get_folder_info(token, folder_id, is_mock=acc.is_mock)
    return info

@router.post("/drive/folders")
async def create_drive_folder(
    req: DriveCreateFolderRequest,
    db: AsyncSession = Depends(get_db)
):
    """Creates a new folder in Google Drive."""
    acc = await get_target_google_account(db, req.account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    try:
        folder = await GoogleDriveService.create_folder(
            access_token=token,
            name=req.name,
            parent_folder_id=req.parent_folder_id,
            is_mock=acc.is_mock
        )
        return {"status": "created", "folder": folder}
    except Exception as e:
        logger.error(f"Failed to create Google Drive folder: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/drive/upload")
async def upload_drive_file(
    file: UploadFile = File(...),
    parent_folder_id: Optional[str] = Form(None),
    account_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Uploads a file to Google Drive."""
    acc = await get_target_google_account(db, account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    content = await file.read()
    try:
        res = await GoogleDriveService.upload_file(
            access_token=token,
            filename=file.filename,
            content_bytes=content,
            mime_type=file.content_type or "application/octet-stream",
            parent_folder_id=parent_folder_id,
            is_mock=acc.is_mock
        )
        return {"status": "uploaded", "file": res}
    except Exception as e:
        logger.error(f"Failed to upload file to Drive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/drive/files/{file_id}")
async def rename_drive_file(
    file_id: str,
    req: DriveRenameRequest,
    db: AsyncSession = Depends(get_db)
):
    """Renames a file or folder in Google Drive."""
    acc = await get_target_google_account(db, req.account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    try:
        res = await GoogleDriveService.rename_file(
            access_token=token,
            file_id=file_id,
            new_name=req.new_name,
            is_mock=acc.is_mock
        )
        return {"status": "renamed", "file": res}
    except Exception as e:
        logger.error(f"Failed to rename file on Drive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/drive/files/{file_id}")
async def delete_drive_file(
    file_id: str,
    account_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Deletes a file or folder from Google Drive."""
    acc = await get_target_google_account(db, account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    try:
        res = await GoogleDriveService.delete_file(
            access_token=token,
            file_id=file_id,
            is_mock=acc.is_mock
        )
        return res
    except Exception as e:
        logger.error(f"Failed to delete file on Drive: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{file_id}/meta")
async def get_google_file_meta(
    file_id: str,
    file_type: str = Query("doc", description="doc, sheet, slide"),
    account_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Fetches structural metadata for Google Workspace file (e.g. tabs for sheet, slides count)."""
    acc = await get_target_google_account(db, account_id)
    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    t = file_type.lower()
    try:
        drive_meta = await GoogleDriveService.get_file_metadata(token, file_id, is_mock=acc.is_mock)
        mime = drive_meta.get("mimeType", "").lower()
        name = drive_meta.get("name", "")
        is_native = mime.startswith("application/vnd.google-apps.")
        if not is_native or name.lower().endswith((".docx", ".xlsx", ".pptx", ".pdf", ".doc", ".xls", ".ppt")):
            return {
                "title": name or "Office Document",
                "format": t,
                "is_office_file": True,
                "total_segments": 0
            }

        if "sheet" in t:
            meta = await GoogleSheetsService.get_metadata(token, file_id, is_mock=acc.is_mock)
        elif "slide" in t:
            meta = await GoogleSlidesService.get_metadata(token, file_id, is_mock=acc.is_mock)
        else:
            meta = await GoogleDocsService.get_metadata(token, file_id, is_mock=acc.is_mock)
        return meta
    except Exception as e:
        logger.warning(f"Failed to fetch metadata for Google file {file_id}: {e}")
        return {
            "title": "Document",
            "format": t,
            "total_segments": 0,
            "error": str(e)
        }

@router.post("/translate")
async def start_google_translation(
    req: GoogleTranslationStartRequest,
    db: AsyncSession = Depends(get_db)
):
    """Initiates an asynchronous background translation job for a Google Doc, Sheet, or Slide."""
    acc = await get_target_google_account(db, req.account_id)

    norm_type = req.file_type.lower().replace("google-apps.", "")
    if "sheet" in norm_type:
        f_type = "gsheet"
    elif "slide" in norm_type or "presentation" in norm_type:
        f_type = "gslide"
    else:
        f_type = "gdoc"

    # 1. Create or update DocumentFile record
    doc_file = DocumentFile(
        project_id=req.project_id,
        filename=req.title,
        file_type=f_type,
        file_size=0,
        original_path=req.file_id,
        detected_language=req.source_language or "ja",
        unit_count=1,
        unit_label="tabs" if f_type == "gsheet" else ("slides" if f_type == "gslide" else "sections")
    )
    db.add(doc_file)
    await db.commit()
    await db.refresh(doc_file)

    # 2. Create DocumentJob record
    options_dict = {
        "file_id": req.file_id,
        "file_type": f_type,
        "title": req.title,
        "account_id": acc.id,
        "selected_sheets": req.selected_sheets,
        "translate_notes": req.translate_notes,
        "parent_folder_id": req.parent_folder_id,
        "translate_images": req.translate_images,
        "ocr_mode": req.ocr_mode,
        "convert_to_google_format": req.convert_to_google_format,
        "target_filename": req.target_filename.strip() if req.target_filename else None
    }

    job = DocumentJob(
        document_id=doc_file.id,
        project_id=req.project_id,
        status="queued",
        source_language=req.source_language,
        target_language=req.target_language,
        provider=req.provider or "gemini",
        model=req.model or "gemini-3.7-flash",
        style=req.style or "Business",
        options_json=json.dumps(options_dict, ensure_ascii=False),
        current_stage="Khởi tạo tác vụ dịch Google Workspace..."
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 3. Launch background worker
    google_job_manager.start_job(job.id)

    return {
        "status": "queued",
        "job_id": job.id,
        "document_id": doc_file.id,
        "title": req.title,
        "file_type": f_type,
        "message": f"Đã khởi tạo tiến trình dịch Google {f_type.upper()}."
    }

# Backward compatible routes that trigger async jobs or synchronous fallback
@router.post("/docs/{file_id}/translate")
async def translate_google_doc(
    file_id: str,
    req: GoogleDocTranslateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Asynchronously translates Google Doc and returns job tracking details."""
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Google Workspace is not connected.")

    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    doc_content = await GoogleDocsService.get_document_content(token, file_id, is_mock=acc.is_mock)
    title = doc_content.get("title", "Google Doc")

    start_req = GoogleTranslationStartRequest(
        file_id=file_id,
        file_type="gdoc",
        title=title,
        target_language=req.target_language,
        project_id=req.project_id,
        style=req.style,
        provider=req.provider,
        model=req.model or "gemini-3.7-flash"
    )
    return await start_google_translation(start_req, db)

@router.post("/sheets/{file_id}/translate")
async def translate_google_sheet(
    file_id: str,
    req: GoogleSheetTranslateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Asynchronously translates Google Sheet and returns job tracking details."""
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Google Workspace is not connected.")

    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    sheet_data = await GoogleSheetsService.get_spreadsheet(token, file_id, is_mock=acc.is_mock)
    title = sheet_data.get("properties", {}).get("title", "Google Sheet")

    start_req = GoogleTranslationStartRequest(
        file_id=file_id,
        file_type="gsheet",
        title=title,
        target_language=req.target_language,
        project_id=req.project_id,
        style=req.style,
        provider=req.provider,
        model=req.model or "gemini-3.7-flash",
        selected_sheets=req.selected_sheets
    )
    return await start_google_translation(start_req, db)

@router.post("/slides/{file_id}/translate")
async def translate_google_slide(
    file_id: str,
    req: GoogleDocTranslateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Asynchronously translates Google Slide presentation."""
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Google Workspace is not connected.")

    token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
    pres_data = await GoogleSlidesService.get_presentation(token, file_id, is_mock=acc.is_mock)
    title = pres_data.get("title", "Google Slide Presentation")

    start_req = GoogleTranslationStartRequest(
        file_id=file_id,
        file_type="gslide",
        title=title,
        target_language=req.target_language,
        project_id=req.project_id,
        style=req.style,
        provider=req.provider,
        model=req.model or "gemini-3.7-flash",
        translate_notes=True
    )
    return await start_google_translation(start_req, db)

# Progress & Job Controls
@router.get("/jobs/{job_id}/progress")
async def get_google_job_progress(job_id: str, db: AsyncSession = Depends(get_db)):
    """Polling endpoint for frontend to monitor Google Workspace translation progress."""
    job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    doc = (await db.execute(select(DocumentFile).where(DocumentFile.id == job.document_id))).scalar_one_or_none()
    issue_cnt = (await db.execute(select(func.count(DocumentIssue.id)).where(DocumentIssue.job_id == job.id))).scalar() or 0

    return {
        "job_id": job.id,
        "status": job.status,
        "filename": doc.filename if doc else "Google File",
        "file_type": doc.file_type if doc else "gdoc",
        "progress_percent": job.progress_percent,
        "total_segments": job.total_segments,
        "completed_segments": job.completed_segments,
        "failed_segments": job.failed_segments,
        "current_stage": job.current_stage,
        "output_filename": job.output_filename,
        "output_path": job.output_path,
        "issues_count": issue_cnt,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None
    }

@router.post("/jobs/{job_id}/pause")
async def pause_google_job(job_id: str):
    google_job_manager.pause_job(job_id)
    return {"message": "Google Job pause requested."}

@router.post("/jobs/{job_id}/resume")
async def resume_google_job(job_id: str):
    google_job_manager.resume_job(job_id)
    return {"message": "Google Job resume requested."}

@router.post("/jobs/{job_id}/cancel")
async def cancel_google_job(job_id: str):
    google_job_manager.cancel_job(job_id)
    return {"message": "Google Job cancellation requested."}

@router.post("/jobs/{job_id}/retry")
async def retry_google_job(job_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    try:
        body = await request.json()
    except Exception:
        body = {}

    if body.get("provider"):
        job.provider = body.get("provider")
    if body.get("model"):
        job.model = str(body.get("model")).strip()

    # Reset failed segments
    failed_segs = (await db.execute(select(DocumentSegment).where(DocumentSegment.job_id == job_id, DocumentSegment.status == "failed"))).scalars().all()
    for s in failed_segs:
        s.status = "pending"
        s.error_message = None

    job.status = "queued"
    job.error_message = None
    job.current_stage = "Job retry queued"
    await db.commit()

    google_job_manager.start_job(job.id)
    return {"message": "Job retry scheduled.", "job_id": job.id, "status": job.status}

# Segment Review & QA
@router.get("/jobs/{job_id}/segments")
async def get_google_job_segments(
    job_id: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves segments for the Google Workspace Review screen."""
    total = (await db.execute(select(func.count(DocumentSegment.id)).where(DocumentSegment.job_id == job_id))).scalar() or 0
    query = (
        select(DocumentSegment)
        .where(DocumentSegment.job_id == job_id)
        .order_by(DocumentSegment.segment_index.asc())
        .offset(offset)
        .limit(limit)
    )
    segments = (await db.execute(query)).scalars().all()

    items = []
    for s in segments:
        loc = {}
        try:
            loc = json.loads(s.location_json or "{}")
        except Exception:
            pass

        items.append({
            "id": s.id,
            "segment_id": s.id,
            "job_id": s.job_id,
            "segment_index": s.segment_index,
            "unit_name": s.context_hint or f"Segment #{s.segment_index + 1}",
            "location": loc,
            "source_text": s.source_text,
            "translated_text": s.translated_text or "",
            "target_text": s.translated_text or "",
            "status": s.status,
            "user_edited": s.status == "user_edited",
            "context_hint": s.context_hint,
            "error_message": s.error_message
        })

    return {
        "total": total,
        "segments": items
    }

@router.patch("/jobs/{job_id}/segments/{segment_id}")
async def update_google_job_segment(
    job_id: str,
    segment_id: str,
    payload: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Updates translated text for a segment."""
    seg = (await db.execute(select(DocumentSegment).where(DocumentSegment.id == segment_id, DocumentSegment.job_id == job_id))).scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found.")

    new_text = payload.get("translated_text") or payload.get("target_text")
    if new_text is not None:
        seg.translated_text = str(new_text)
        seg.status = "user_edited"
        await db.commit()

    return {
        "id": seg.id,
        "segment_index": seg.segment_index,
        "source_text": seg.source_text,
        "translated_text": seg.translated_text,
        "status": seg.status
    }

@router.post("/jobs/{job_id}/segments/{segment_id}/regenerate")
async def regenerate_google_job_segment(
    job_id: str,
    segment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Regenerates a single Google document segment using AI."""
    job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
    seg = (await db.execute(select(DocumentSegment).where(DocumentSegment.id == segment_id, DocumentSegment.job_id == job_id))).scalar_one_or_none()
    if not job or not seg:
        raise HTTPException(status_code=404, detail="Job or segment not found.")

    provider = provider_registry.get_provider(job.provider) or provider_registry.get_provider("gemini")
    prompt = f"""Translate this single text from {job.source_language.upper()} to {job.target_language.upper()} with style {job.style}.
Source: {seg.source_text}

Preserve all numbers, punctuation, and formatting tags. Return only the translated text."""

    try:
        resp = await provider.generate(prompt=prompt, model=job.model, temperature=0.2)
        new_text = resp.text.strip().strip('"')
        token_map = json.loads(seg.protected_tokens_json or "{}")
        restored, _ = TokenProtector.restore_tokens(new_text, token_map)
        seg.translated_text = restored
        seg.status = "translated"
        seg.error_message = None
        await db.commit()

        return {
            "id": seg.id,
            "source_text": seg.source_text,
            "translated_text": seg.translated_text,
            "status": seg.status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")

@router.get("/jobs/{job_id}/issues")
async def get_google_job_issues(job_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves QA issues associated with this job."""
    issues = (await db.execute(select(DocumentIssue).where(DocumentIssue.job_id == job_id))).scalars().all()
    return [{
        "id": i.id,
        "job_id": i.job_id,
        "segment_id": i.segment_id,
        "severity": i.severity,
        "category": i.category,
        "location_text": i.location_text,
        "message": i.message,
        "created_at": i.created_at.isoformat() if i.created_at else ""
    } for i in issues]
