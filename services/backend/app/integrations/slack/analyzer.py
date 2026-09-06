import re
from typing import Dict, List, Any

class SlackMessageAnalyzer:
    """Classifies Slack messages and determines translation relevance priority score."""

    # Keywords patterns for IT Comtor / BrSE communications
    QUESTION_PATTERNS = [r"でしょうか", r"ですか", r"可能でしょうか", r"教えて", r"確認させて", r"いつ頃", r"何時", r"\?|？"]
    BUG_PATTERNS = [r"バグ", r"エラー", r"不具合", r"障害", r"動かない", r"落ちる", r"500", r"404", r"crash", r"bug", r"error", r"issue"]
    REQUIREMENT_PATTERNS = [r"仕様", r"要件", r"機能", r"変更", r"追加", r"実装", r"画面", r"API", r"DB", r"設計"]
    ACTION_PATTERNS = [r"至急", r"お願いします", r"対応", r"修正", r"調査", r"確認", r"至急", r"ASAP", r"fix", r"check"]
    DEADLINE_PATTERNS = [r"納期", r"締切", r"期限", r"リリース", r"スケジュール", r"までに", r"本日中", r"明日"]
    GREETING_PATTERNS = [r"おはよう", r"お疲れ様", r"よろしく", r"こんにちは", r"こんばんは"]

    @classmethod
    def analyze_message(cls, text: str) -> Dict[str, Any]:
        """Analyzes text and returns primary category, tags, and translation priority score (0-100)."""
        tags: List[str] = []
        score = 40 # Base score

        # Check Greetings
        if any(re.search(p, text, re.IGNORECASE) for p in cls.GREETING_PATTERNS) and len(text) < 30:
            return {
                "category": "FYI",
                "tags": ["GREETING"],
                "priority_score": 25,
                "action_recommended": "none"
            }

        # Check Bug / Error
        if any(re.search(p, text, re.IGNORECASE) for p in cls.BUG_PATTERNS):
            tags.append("BUG")
            score += 30

        # Check Question
        if any(re.search(p, text, re.IGNORECASE) for p in cls.QUESTION_PATTERNS):
            tags.append("QUESTION")
            score += 25

        # Check Action Required
        if any(re.search(p, text, re.IGNORECASE) for p in cls.ACTION_PATTERNS):
            tags.append("ACTION_REQUIRED")
            score += 20

        # Check Deadline
        if any(re.search(p, text, re.IGNORECASE) for p in cls.DEADLINE_PATTERNS):
            tags.append("DEADLINE")
            score += 15

        # Check Requirements / Tech
        if any(re.search(p, text, re.IGNORECASE) for p in cls.REQUIREMENT_PATTERNS):
            tags.append("TECHNICAL")
            score += 15

        priority_score = min(100, score)
        primary_category = tags[0] if tags else "NORMAL"

        action_recommended = "none"
        if priority_score >= 85:
            action_recommended = "translate_and_suggest_reply"
        elif priority_score >= 60:
            action_recommended = "translate"

        return {
            "category": primary_category,
            "tags": tags,
            "priority_score": priority_score,
            "action_recommended": action_recommended
        }
