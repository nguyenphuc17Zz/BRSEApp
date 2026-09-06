import time
import json
from typing import Dict, List, Optional, Tuple, Any
import httpx
from app.core.logging import logger
from app.providers.base import AIProvider, ProviderResponseData

class OllamaProvider(AIProvider):
    """Local Ollama AI Provider Adapter using REST API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        default_model: str = "gemma4:12b",
        embed_model: str = "nomic-embed-text:latest"
    ):
        super().__init__(name="ollama", api_key=None, base_url=base_url.rstrip("/"), default_model=default_model)
        self.embed_model = embed_model

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        json_mode: bool = True,
        max_tokens: Optional[int] = None,
        timeout: float = 120.0,
        **kwargs: Any
    ) -> ProviderResponseData:
        start_time = time.time()
        active_model = model or self.default_model or "gemma4:12b"
        url = f"{self.base_url}/api/chat"

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": active_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }

        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            latency_ms = int((time.time() - start_time) * 1000)

            if resp.status_code != 200:
                error_body = resp.text
                logger.error(f"Ollama API error (Status {resp.status_code}): {error_body}")
                raise RuntimeError(f"Ollama returned status {resp.status_code}: {error_body}")

            data = resp.json()
            generated_text = data.get("message", {}).get("content", "")

            return ProviderResponseData(
                text=generated_text.strip(),
                model=active_model,
                provider="ollama",
                latency_ms=latency_ms,
                raw_response=data
            )

    async def health_check(self) -> Tuple[bool, str, List[str]]:
        try:
            url = f"{self.base_url}/api/tags"
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    # 100% of all models returned by Ollama API
                    models = [m["name"] for m in data.get("models", [])]
                    return True, f"Connected to local Ollama. {len(models)} models available.", models
                else:
                    return False, f"Ollama HTTP {resp.status_code}: {resp.text}", []
        except Exception as e:
            return False, f"Ollama local service is not reachable at {self.base_url}: {str(e)}", []

    async def list_models(self) -> List[str]:
        """Fetches 100% of models live from Ollama API."""
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to fetch live Ollama models: {e}")
        return []

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Generates embedding vector using local Ollama model (e.g. nomic-embed-text)."""
        if not text:
            return None
        try:
            url = f"{self.base_url}/api/embeddings"
            payload = {
                "model": self.embed_model,
                "prompt": text
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return resp.json().get("embedding")
        except Exception as e:
            logger.warning(f"Failed to generate embedding via Ollama: {e}")
        return None
