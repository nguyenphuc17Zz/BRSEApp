from typing import Dict, Any, Optional
from app.core.logging import logger
from app.integrations.desktop.app_detector import WindowsAppDetector
from app.integrations.desktop.profiles import DesktopProfileManager
from app.integrations.desktop.clipboard import ClipboardService

class DesktopAgent:
    """Coordinates Windows foreground application detection, clipboard capture, and quick actions."""

    def __init__(self):
        self.shortcuts = {
            "quick_translate": "Ctrl+Shift+T",
            "quick_reply": "Ctrl+Shift+R",
            "quick_explain": "Ctrl+Shift+E"
        }
        self.is_running = True

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": "running" if self.is_running else "stopped",
            "shortcuts": self.shortcuts,
            "clipboard_available": True,
            "active_window": WindowsAppDetector.get_foreground_window_info()
        }

    def update_shortcuts(self, shortcuts: Dict[str, str]):
        self.shortcuts.update(shortcuts)
        logger.info(f"Desktop shortcuts updated: {self.shortcuts}")

    def capture_context_and_text(self, override_text: Optional[str] = None) -> Dict[str, Any]:
        """Gathers text from selection/clipboard + active window info + app profile."""
        text = override_text or ClipboardService.get_text()
        win_info = WindowsAppDetector.get_foreground_window_info()
        profile = DesktopProfileManager.get_profile_for_app(win_info.get("process_name", ""))

        return {
            "source_text": text,
            "window_info": win_info,
            "profile": profile
        }

desktop_agent = DesktopAgent()
