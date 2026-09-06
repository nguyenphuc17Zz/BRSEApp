import time
import json
import re
import random
import asyncio
from typing import Dict, List, Optional, Tuple, Any
import httpx
from app.core.logging import logger
from app.providers.base import AIProvider, ProviderResponseData

class GroqProvider(AIProvider):
    """Groq Cloud AI Provider Adapter using OpenAI-compatible REST API."""

    def __init__(self, api_key: str, default_model: str = "openai/gpt-oss-120b"):
        super().__init__(name="groq", api_key=api_key, default_model=default_model)
        self.base_url = "https://api.groq.com/openai/v1"

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = True,
        timeout: float = 60.0,
        max_tokens: Optional[int] = None
    ) -> ProviderResponseData:
        start_time = time.time()
        active_model = model or self.default_model or "openai/gpt-oss-120b"
        if active_model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            active_model = "openai/gpt-oss-120b"
        url = f"{self.base_url}/chat/completions"

        messages = []
        sys_content = (system_instruction or "You are a helpful bilingual assistant.").strip()
        if json_mode and "json" not in sys_content.lower():
            sys_content += " You must respond in valid JSON format."
        if sys_content:
            messages.append({"role": "system", "content": sys_content})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": active_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 3200,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Safe high-speed models verified active on Groq
        models_to_try = [active_model]
        for fb in ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound-mini", "qwen/qwen3.6-27b"]:
            if fb not in models_to_try:
                models_to_try.append(fb)

        last_error = None
        min_cooldown = None
        for current_model in models_to_try:
            # Skip models with small context windows when prompt is large
            if "allam" in current_model.lower() and (len(prompt) + len(sys_content)) > 4000:
                continue

            payload["model"] = current_model
            if json_mode:
                if "qwen" in current_model.lower():
                    # For Qwen reasoning models, hide internal thinking tokens so output produces direct clean JSON
                    payload["reasoning_format"] = "hidden"
                    payload.pop("response_format", None)
                elif any(k in current_model.lower() for k in ["compound", "gpt-oss"]):
                    payload["response_format"] = {"type": "json_object"}
                    payload.pop("reasoning_format", None)
                else:
                    payload.pop("response_format", None)
                    payload.pop("reasoning_format", None)
            else:
                if "qwen" in current_model.lower():
                    payload["reasoning_format"] = "hidden"
                else:
                    payload.pop("reasoning_format", None)
                payload.pop("response_format", None)

            # Dynamic TPM Guard: estimate prompt input tokens and enforce strict 7,200 total token budget
            est_input_tokens = (len(prompt) + len(sys_content)) // 2
            safe_ceiling = max(400, 7200 - est_input_tokens)

            # Model constraints: Qwen has 1,000 OTPM limit on Groq Free Tier
            if "qwen" in current_model.lower():
                model_limit = 800
            else:
                model_limit = min(2000, safe_ceiling)

            target_max = max_tokens or model_limit
            payload["max_tokens"] = max(350, min(target_max, model_limit, safe_ceiling))

            max_attempts = 2
            for attempt in range(max_attempts):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.post(url, json=payload, headers=headers)
                        latency_ms = int((time.time() - start_time) * 1000)

                        if resp.status_code == 200:
                            data = resp.json()
                            choices = data.get("choices", [])
                            if not choices:
                                raise RuntimeError("Groq returned no choices.")

                            generated_text = choices[0].get("message", {}).get("content", "")
                            return ProviderResponseData(
                                text=generated_text.strip(),
                                model=current_model,
                                provider="groq",
                                latency_ms=latency_ms,
                                raw_response=data
                            )

                        error_body = resp.text
                        if resp.status_code in (429, 503):
                            # Check if error specifies hours or minutes (daily TPD limit reached)
                            if re.search(r"(?:try again in|retry in)\s*[0-9]+[hm]", error_body, re.IGNORECASE):
                                wait_sec = 3600.0
                            else:
                                match = re.search(r"(?:try again in|retry in)\s*([0-9.]+)\s*s\b", error_body, re.IGNORECASE)
                                if match:
                                    wait_sec = float(match.group(1)) + random.uniform(0.3, 0.6)
                                elif "retry-after" in resp.headers:
                                    try:
                                        wait_sec = float(resp.headers["retry-after"]) + 0.5
                                    except Exception:
                                        wait_sec = 3.0
                                else:
                                    wait_sec = 3.0

                            if min_cooldown is None or wait_sec < min_cooldown:
                                min_cooldown = wait_sec

                            # Guard: If wait time is > 8.0s, fast-switch to next model in fallback chain!
                            if wait_sec > 8.0:
                                logger.warning(
                                    f"Groq {resp.status_code} on model '{current_model}' requested {wait_sec:.1f}s wait (>8s). Fast-switching to next model in fallback chain..."
                                )
                                break

                            if attempt < (max_attempts - 1):
                                actual_sleep = min(wait_sec, 8.0)
                                logger.warning(
                                    f"Groq {resp.status_code} on model '{current_model}'. Waiting {actual_sleep:.1f}s before retry (attempt {attempt + 1}/{max_attempts})..."
                                )
                                await asyncio.sleep(actual_sleep)
                                continue


                        logger.error(f"Groq API error (Status {resp.status_code}) for model {current_model}: {error_body}")
                        try:
                            msg = resp.json().get("error", {}).get("message", error_body)
                        except Exception:
                            msg = error_body
                        last_error = RuntimeError(f"Groq API returned status {resp.status_code}: {msg}")
                        break
                except httpx.RequestError as exc:
                    logger.warning(f"Network error on Groq request to {current_model}: {exc}")
                    last_error = exc
                    if attempt < (max_attempts - 1):
                        await asyncio.sleep(2.0)
                        continue
                    break

        # Fallback rescue: If all models failed due to rolling rate limits, wait the cooldown and retry top model once!
        if min_cooldown and min_cooldown <= 45.0:
            sleep_duration = min(min_cooldown, 35.0)
            logger.warning(
                f"All Groq models currently rate-limited. Waiting {sleep_duration:.1f}s for quota window to reset before final retry on '{models_to_try[0]}'..."
            )
            await asyncio.sleep(sleep_duration)
            rescue_model = models_to_try[0]
            payload["model"] = rescue_model
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            generated_text = choices[0].get("message", {}).get("content", "")
                            return ProviderResponseData(
                                text=generated_text.strip(),
                                model=rescue_model,
                                provider="groq",
                                latency_ms=int((time.time() - start_time) * 1000),
                                raw_response=data
                            )
            except Exception as rescue_exc:
                logger.warning(f"Rescue attempt failed: {rescue_exc}")

        raise last_error or RuntimeError("Groq generation failed.")

    async def health_check(self) -> Tuple[bool, str, List[str]]:
        if not self.api_key:
            return False, "Groq API key is not configured.", []
        try:
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    # 100% of all models returned by Groq API
                    models = [m["id"] for m in data.get("data", [])]
                    return True, f"Connected to Groq Cloud. {len(models)} models available.", models
                else:
                    return False, f"HTTP {resp.status_code}: {resp.text}", []
        except Exception as e:
            return False, f"Connection failed: {str(e)}", []

    async def list_models(self) -> List[str]:
        """Fetches 100% of models live from Groq API."""
        if not self.api_key:
            return []
        try:
            url = f"{self.base_url}/models"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            logger.warning(f"Failed to fetch live Groq models: {e}")
        return []
