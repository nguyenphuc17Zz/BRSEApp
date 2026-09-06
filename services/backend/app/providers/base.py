from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel

class ProviderResponseData(BaseModel):
    text: str
    model: str
    provider: str
    latency_ms: int
    raw_response: Optional[Any] = None

class AIProvider(ABC):
    """Abstract base class for all AI model providers (Gemini, Groq, Ollama)."""

    def __init__(self, name: str, api_key: Optional[str] = None, base_url: Optional[str] = None, default_model: Optional[str] = None):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model

    @abstractmethod
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
        """Generates text from the AI model."""
        pass

    @abstractmethod
    async def health_check(self) -> Tuple[bool, str, List[str]]:
        """Verifies connection and returns (is_healthy, status_message, list_of_available_models)."""
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Lists available models for this provider."""
        pass

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Optionally generates embedding vector for semantic search."""
        return None
