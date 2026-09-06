from typing import Dict, Any, Optional

DEFAULT_APP_PROFILES = {
    "slack.exe": {"mode": "conversation", "label": "Slack Conversation", "style": "Polite"},
    "winword.exe": {"mode": "document", "label": "Word Document", "style": "Formal"},
    "excel.exe": {"mode": "table", "label": "Excel Table/Data", "style": "Technical"},
    "powerpnt.exe": {"mode": "presentation", "label": "PowerPoint Presentation", "style": "Polite"},
    "chrome.exe": {"mode": "web", "label": "Web Browser", "style": "Auto"},
    "msedge.exe": {"mode": "web", "label": "Edge Browser", "style": "Auto"},
    "code.exe": {"mode": "technical", "label": "VS Code Source/Config", "style": "Technical"},
    "notepad.exe": {"mode": "generic", "label": "Text Editor", "style": "Auto"}
}

class DesktopProfileManager:
    """Matches active foreground window to contextual application profiles."""

    @classmethod
    def get_profile_for_app(cls, process_name: str) -> Dict[str, Any]:
        p = process_name.lower()
        for key, conf in DEFAULT_APP_PROFILES.items():
            if key in p:
                return conf
        return {"mode": "generic", "label": "Desktop Application", "style": "Auto"}

    @classmethod
    def match_project_from_title(cls, window_title: str, projects: list) -> Optional[Any]:
        """Infers active project workspace by matching project code or name in the window title."""
        if not window_title or not projects:
            return None
        t = window_title.lower()
        for proj in projects:
            if proj.code.lower() in t or proj.name.lower() in t:
                return proj
        return None
