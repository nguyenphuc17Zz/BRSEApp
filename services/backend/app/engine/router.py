import re
from typing import Dict, List, Optional, Tuple, Any
from app.core.logging import logger
from app.core.security import scan_sensitive_data

class TaskAnalyzer:
    """Analyzes translation input to determine task complexity and characteristics."""

    # Japanese IT / Technical keywords
    IT_KEYWORDS = {
        "api", "endpoint", "token", "oauth", "db", "sql", "null", "boolean",
        "障害", "認証", "認可", "要件", "仕様", "設計", "リリース", "バグ", "デプロイ",
        "テーブル", "カラム", "インデックス", "非同期", "例外", "レスポンス", "リクエスト",
        "サーバー", "クライアント", "環境", "本番", "ステージング", "検証", "テスト"
    }

    # Ambiguity trigger words in Japanese business IT
    AMBIGUITY_TRIGGERS = {
        "対象外", "対応", "検討", "確認", "仕様", "想定", "方針", "見送り", "調整", "扱い"
    }

    @classmethod
    def analyze(cls, text: str, project_has_rules: bool = False) -> Dict[str, Any]:
        text_lower = text.lower()
        length = len(text)
        
        # Check sensitive data
        sensitive_items = scan_sensitive_data(text)
        has_sensitive = len(sensitive_items) > 0

        # Technical density check
        it_matches = [kw for kw in cls.IT_KEYWORDS if kw in text_lower or kw in text]
        technical_density = len(it_matches) / max(1, len(text.split()))

        # Ambiguity check
        ambiguous_matches = [tr for tr in cls.AMBIGUITY_TRIGGERS if tr in text]
        is_ambiguous = len(ambiguous_matches) > 0 and length < 100

        # Determine task type
        if is_ambiguous:
            task_type = "ambiguous_translation"
        elif technical_density > 0.15 or len(it_matches) >= 2:
            task_type = "technical_translation"
        elif length > 400:
            task_type = "large_context"
        elif length < 40 and len(it_matches) == 0:
            task_type = "simple_translation"
        else:
            task_type = "business_translation"

        return {
            "task_type": task_type,
            "has_sensitive": has_sensitive,
            "it_keywords": it_matches,
            "is_ambiguous": is_ambiguous,
            "ambiguous_keywords": ambiguous_matches,
            "length": length
        }

class RoutingEngine:
    """Determines provider and model selection based on task analysis and policy."""

    def select_route(
        self,
        analysis: Dict[str, Any],
        preferred_provider: Optional[str] = None,
        available_providers: Optional[List[str]] = None
    ) -> Tuple[str, List[str], str]:
        """
        Returns (primary_provider, fallback_providers, recommended_model).
        Policy principle: quality > reliability > cost > latency.
        """
        all_available = available_providers or ["gemini", "groq", "ollama"]

        # If user explicitly preferred a provider that is available, honor it
        if preferred_provider and preferred_provider in all_available:
            primary = preferred_provider
            fallbacks = [p for p in ["gemini", "groq", "ollama"] if p != primary and p in all_available]
            return primary, fallbacks, self._default_model_for(primary)

        # Sensitive local routing policy
        if analysis.get("has_sensitive") and "ollama" in all_available:
            logger.info("Sensitive data detected in source text; routing to local Ollama.")
            return "ollama", [p for p in all_available if p != "ollama"], "gemma4:12b"

        task_type = analysis.get("task_type", "business_translation")

        if task_type in ("ambiguous_translation", "technical_translation"):
            # Strongest reasoning model for complex/ambiguous IT content
            order = ["gemini", "groq", "ollama"]
        elif task_type == "simple_translation":
            # High speed / cheap model
            order = ["groq", "gemini", "ollama"]
        else:
            order = ["gemini", "groq", "ollama"]

        ordered_available = [p for p in order if p in all_available]
        if not ordered_available:
            ordered_available = all_available

        primary = ordered_available[0]
        fallbacks = ordered_available[1:]
        model = self._default_model_for(primary)

        return primary, fallbacks, model

    def _default_model_for(self, provider: str) -> str:
        if provider == "gemini":
            return "gemini-3.5-flash-lite"
        elif provider == "groq":
            return "llama-3.3-70b-versatile"
        elif provider == "ollama":
            return "gemma4:12b"
        return "default"

router_engine = RoutingEngine()
