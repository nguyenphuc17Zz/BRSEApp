import ctypes
import os
from typing import Dict, Any, Optional
from app.core.logging import logger

class WindowsAppDetector:
    """Detects foreground window, window title, and executable process name on Windows."""

    @classmethod
    def get_foreground_window_info(cls) -> Dict[str, Any]:
        """Returns details about the current active window and application."""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return {
                    "hwnd": 0,
                    "title": "Desktop / None",
                    "process_name": "unknown.exe",
                    "pid": 0
                }

            # 1. Window Title
            length = user32.GetWindowTextLengthW(hwnd)
            title_buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buff, length + 1)
            window_title = title_buff.value

            # 2. Process ID
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_id = pid.value

            # 3. Process Executable Name
            process_name = "unknown.exe"
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, proc_id)
            if h_process:
                try:
                    exe_buff = ctypes.create_unicode_buffer(1024)
                    size = ctypes.c_ulong(1024)
                    # QueryFullProcessImageNameW
                    if kernel32.QueryFullProcessImageNameW(h_process, 0, exe_buff, ctypes.byref(size)):
                        process_name = os.path.basename(exe_buff.value)
                finally:
                    kernel32.CloseHandle(h_process)

            return {
                "hwnd": hwnd,
                "title": window_title,
                "process_name": process_name.lower(),
                "pid": proc_id
            }
        except Exception as e:
            logger.debug(f"Foreground window detection notice: {e}")
            return {
                "hwnd": 0,
                "title": "Active Desktop Window",
                "process_name": "browser.exe",
                "pid": 0
            }
