import time
import json
import re
import random
import asyncio
from typing import Dict, List, Optional, Tuple, Any
import httpx
from app.core.logging import logger
from app.providers.base import AIProvider, ProviderResponseData

class GeminiProvider(AIProvider):
    """Google Gemini AI Provider Adapter using direct async REST API."""

    def __init__(self, api_key: str, default_model: str = "gemini-3.7-flash"):
        super().__init__(name="gemini", api_key=api_key, default_model=default_model)
        self.base_api_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = True,
        max_tokens: Optional[int] = None,
        timeout: float = 60.0,
        **kwargs: Any
    ) -> ProviderResponseData:
        start_time = time.time()
        active_model = model or self.default_model or "gemini-3.7-flash"
        # Auto-map retired/deprecated models
        if active_model == "gemini-2.5-flash":
            active_model = "gemini-3.7-flash"

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.95,
            }
        }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Models to attempt: prioritize requested active_model, then resilient fallbacks
        models_to_try = [active_model]
        for fallback in ["gemini-3.7-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error = None
        read_timeout = min(timeout, 35.0)
        client_timeout = httpx.Timeout(timeout, connect=8.0, read=read_timeout)

        for current_model in models_to_try:
            max_attempts = 2 if current_model == active_model else 1
            url = f"{self.base_api_url}/models/{current_model}:generateContent?key={self.api_key}"
            for attempt in range(max_attempts):
                try:
                    async with httpx.AsyncClient(timeout=client_timeout) as client:
                        resp = await client.post(url, json=payload)
                        latency_ms = int((time.time() - start_time) * 1000)

                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if not candidates:
                                raise RuntimeError("Gemini returned no candidates in response.")

                            content_parts = candidates[0].get("content", {}).get("parts", [])
                            generated_text = "".join(part.get("text", "") for part in content_parts)

                            return ProviderResponseData(
                                text=generated_text.strip(),
                                model=current_model,
                                provider="gemini",
                                latency_ms=latency_ms,
                                raw_response=data
                            )
                        elif resp.status_code in (503, 429) and attempt < (max_attempts - 1):
                            wait_sec = 4.0
                            match = re.search(r"(?:retry in|retryDelay[\":\s]+)\s*([0-9.]+)\s*s?", resp.text, re.IGNORECASE)
                            if match:
                                wait_sec = min(float(match.group(1)) + random.uniform(0.3, 0.8), 20.0)
                            elif resp.status_code == 503:
                                wait_sec = 3.0 + random.uniform(0.5, 1.5)

                            logger.warning(
                                f"Gemini model {current_model} returned status {resp.status_code} (attempt {attempt + 1}/{max_attempts}). Waiting {wait_sec:.1f}s before retry..."
                            )
                            await asyncio.sleep(wait_sec)
                            continue
                        else:
                            error_body = resp.text
                            logger.warning(f"Gemini API error (Status {resp.status_code}) for model {current_model}: {error_body}")
                            try:
                                msg = resp.json().get("error", {}).get("message", error_body)
                            except Exception:
                                msg = error_body
                            last_error = RuntimeError(f"Gemini API returned status {resp.status_code}: {msg}")
                            break
                except httpx.RequestError as exc:
                    logger.warning(f"Network error on Gemini request to {current_model}: {exc}")
                    last_error = exc
                    if attempt < (max_attempts - 1):
                        await asyncio.sleep(1.0)
                        continue
                    break

        raise last_error or RuntimeError("Gemini generation failed.")

    async def health_check(self) -> Tuple[bool, str, List[str]]:
        if not self.api_key:
            return False, "Gemini API key is not configured.", []
        try:
            url = f"{self.base_api_url}/models?key={self.api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    # 100% of all models returned by Gemini API
                    models = [
                        m["name"].replace("models/", "")
                        for m in data.get("models", [])
                    ]
                    return True, f"Connected to Google Gemini. {len(models)} models available.", models
                else:
                    return False, f"HTTP {resp.status_code}: {resp.text}", []
        except Exception as e:
            return False, f"Connection failed: {str(e)}", []

    async def list_models(self) -> List[str]:
        """Fetches 100% of models live from Gemini API."""
        if not self.api_key:
            return []
        try:
            url = f"{self.base_api_url}/models?key={self.api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["name"].replace("models/", "") for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to fetch live Gemini models: {e}")
        return []
