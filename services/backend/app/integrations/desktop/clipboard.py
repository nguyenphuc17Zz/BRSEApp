import time
import pyperclip
from app.core.logging import logger

class ClipboardService:
    """Provides safe clipboard reading, writing, and preservation."""

    _saved_clipboard: str = ""

    @classmethod
    def get_text(cls) -> str:
        try:
            return pyperclip.paste() or ""
        except Exception as e:
            logger.debug(f"Clipboard read notice: {e}")
            return ""

    @classmethod
    def set_text(cls, text: str):
        try:
            pyperclip.copy(text)
        except Exception as e:
            logger.debug(f"Clipboard write notice: {e}")

    @classmethod
    def save_state(cls):
        cls._saved_clipboard = cls.get_text()

    @classmethod
    def restore_state(cls):
        if cls._saved_clipboard:
            cls.set_text(cls._saved_clipboard)

    @classmethod
    def capture_selected_text(cls, preserve_clipboard: bool = False) -> str:
        """Captures text from clipboard, optionally preserving the previous state."""
        if preserve_clipboard:
            cls.save_state()

        text = cls.get_text()
        return text.strip()
