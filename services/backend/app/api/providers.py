import json
import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import encrypt_credential, decrypt_credential, mask_api_key
from app.db.models import ProviderConfig
from app.providers.registry import provider_registry
from app.schemas.schemas import ProviderResponse, ProviderUpdate

router = APIRouter(prefix="/api/providers", tags=["AI Providers"])

@router.get("", response_model=List[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    """Lists configured AI providers with masked credentials and real health status."""
    res = await db.execute(select(ProviderConfig).order_by(ProviderConfig.priority.asc()))
    configs = res.scalars().all()

    response = []
    for c in configs:
        plain_key = decrypt_credential(c.api_key_encrypted) if c.api_key_encrypted else None
        response.append(ProviderResponse(
            id=c.id,
            name=c.name,
            display_name=c.display_name,
            api_key_masked=mask_api_key(plain_key),
            base_url=c.base_url,
            default_model=c.default_model,
            available_models=json.loads(c.available_models_json or "[]"),
            priority=c.priority,
            is_enabled=c.is_enabled,
            is_healthy=c.is_healthy,
            health_message=c.health_message,
            last_checked_at=c.last_checked_at
        ))
    return response

@router.patch("/{name}", response_model=ProviderResponse)
async def update_provider(name: str, data: ProviderUpdate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ProviderConfig).where(ProviderConfig.name == name.lower()))
    c = res.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found.")

    if data.api_key is not None and data.api_key.strip():
        c.api_key_encrypted = encrypt_credential(data.api_key.strip())
    if data.display_name is not None:
        c.display_name = data.display_name
    if data.base_url is not None:
        c.base_url = data.base_url
    if data.default_model is not None:
        c.default_model = data.default_model
    if data.priority is not None:
        c.priority = data.priority
    if data.is_enabled is not None:
        c.is_enabled = data.is_enabled

    await db.commit()
    await db.refresh(c)

    # Re-initialize registry with updated credentials
    await provider_registry.initialize(db)

    plain_key = decrypt_credential(c.api_key_encrypted) if c.api_key_encrypted else None
    return ProviderResponse(
        id=c.id,
        name=c.name,
        display_name=c.display_name,
        api_key_masked=mask_api_key(plain_key),
        base_url=c.base_url,
        default_model=c.default_model,
        available_models=json.loads(c.available_models_json or "[]"),
        priority=c.priority,
        is_enabled=c.is_enabled,
        is_healthy=c.is_healthy,
        health_message=c.health_message,
        last_checked_at=c.last_checked_at
    )

@router.post("/{name}/test")
async def test_provider_connection(name: str, db: AsyncSession = Depends(get_db)):
    """Performs live health check on provider and updates status in database."""
    provider = provider_registry.get_provider(name.lower())
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found.")

    is_healthy, msg, models = await provider.health_check()

    # Update provider status in DB
    res = await db.execute(select(ProviderConfig).where(ProviderConfig.name == name.lower()))
    c = res.scalar_one_or_none()
    if c:
        c.is_healthy = is_healthy
        c.health_message = msg
        if models:
            c.available_models_json = json.dumps(models)
        c.last_checked_at = datetime.datetime.utcnow()
        await db.commit()

    return {
        "provider": name,
        "is_healthy": is_healthy,
        "message": msg,
        "models_count": len(models),
        "models": models
    }

@router.post("/{name}/models/refresh")
async def refresh_provider_models(name: str, db: AsyncSession = Depends(get_db)):
    """Queries 100% of live models from the provider API and updates database cache."""
    provider = provider_registry.get_provider(name.lower())
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found.")

    models = await provider.list_models()
    is_healthy = len(models) > 0

    res = await db.execute(select(ProviderConfig).where(ProviderConfig.name == name.lower()))
    c = res.scalar_one_or_none()
    if c:
        c.is_healthy = is_healthy
        c.available_models_json = json.dumps(models)
        c.last_checked_at = datetime.datetime.utcnow()
        if is_healthy:
            c.health_message = f"Synchronized {len(models)} models from live API."
        await db.commit()

    return {
        "provider": name,
        "models_count": len(models),
        "models": models
    }

@router.post("/models/refresh-all")
async def refresh_all_models_endpoint(db: AsyncSession = Depends(get_db)):
    """Refreshes 100% of models from all providers via live API calls."""
    results = await refresh_all_provider_models(db)
    return results

async def refresh_all_provider_models(db: AsyncSession):
    """Internal helper to refresh models from all providers on startup or on-demand."""
    summary = {}
    for name in ["gemini", "groq", "ollama"]:
        provider = provider_registry.get_provider(name)
        if not provider:
            continue
        try:
            models = await provider.list_models()
            is_healthy = len(models) > 0
            res = await db.execute(select(ProviderConfig).where(ProviderConfig.name == name))
            c = res.scalar_one_or_none()
            if c:
                c.is_healthy = is_healthy
                if models:
                    c.available_models_json = json.dumps(models)
                c.last_checked_at = datetime.datetime.utcnow()
                c.health_message = f"Live API synchronized with {len(models)} models."
            summary[name] = {"count": len(models), "models": models}
        except Exception as e:
            summary[name] = {"error": str(e), "count": 0, "models": []}
    await db.commit()
    return summary
