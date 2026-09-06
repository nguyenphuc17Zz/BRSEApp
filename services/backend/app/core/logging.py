import logging
import sys
import re

# Ensure Windows console supports UTF-8 characters (Vietnamese, Japanese) without crashing
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SENSITIVE_PATTERNS = [
    re.compile(r"(key|secret|token|password|bearer|authorization)\s*[:=]\s*['\"]?([^'\"\s,]+)", re.IGNORECASE)
]

class RedactingFormatter(logging.Formatter):
    """Custom logging formatter that strips API keys and secrets from logs."""
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern in SENSITIVE_PATTERNS:
            msg = pattern.sub(r"\1: [REDACTED]", msg)
        return msg

def get_logger(name: str = "comtor_copilot") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = RedactingFormatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

logger = get_logger()
