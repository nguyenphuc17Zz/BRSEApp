import base64
import hashlib
import re
from typing import Dict, List, Optional, Tuple
from cryptography.fernet import Fernet
from app.core.config import settings

def _get_fernet_key(salt: str) -> bytes:
    """Derives a deterministic 32-byte url-safe base64 key from the application secret key."""
    h = hashlib.sha256(salt.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)

_FERNET = Fernet(_get_fernet_key(settings.SECRET_KEY))

def encrypt_credential(plain_text: str) -> str:
    """Encrypts plain text credentials for safe storage in the database."""
    if not plain_text:
        return ""
    return _FERNET.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_credential(cipher_text: str) -> str:
    """Decrypts cipher text stored in the database back to plain text."""
    if not cipher_text:
        return ""
    try:
        return _FERNET.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        # If text is already plain or corrupted, return as is safely
        return cipher_text

def mask_api_key(key: Optional[str]) -> str:
    """Returns a masked version of an API key for safe UI display (e.g., 'gsk_...3a8f')."""
    if not key:
        return ""
    if len(key) <= 8:
        return "********"
    return f"{key[:4]}...{key[-4:]}"

# Regex patterns for sensitive data & PII detection
PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    "phone": re.compile(r"(\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9})"),
    "jwt_token": re.compile(r"ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}\.[A-Za-z0-9._-]{10,}"),
    "api_key_candidate": re.compile(r"(?:api[_-]?key|secret|token|password|bearer)[\s:=]+['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?", re.IGNORECASE),
    "ipv4_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

def scan_sensitive_data(text: str) -> List[Dict[str, str]]:
    """Scans text for sensitive information (PII, tokens, keys) before sending to external AI."""
    findings = []
    if not text:
        return findings

    for kind, pattern in PII_PATTERNS.items():
        matches = pattern.finditer(text)
        for match in matches:
            val = match.group(0)
            # Filter out common false positives for phones like single dates
            if kind == "phone" and len(re.sub(r"\D", "", val)) < 9:
                continue
            findings.append({
                "type": kind,
                "value": mask_api_key(val) if len(val) > 6 else "***",
                "start": match.start(),
                "end": match.end(),
            })
    return findings

def mask_sensitive_data(text: str) -> Tuple[str, List[Dict[str, str]]]:
    """Replaces sensitive data in text with placeholder tokens [REDACTED_<TYPE>]."""
    findings = scan_sensitive_data(text)
    if not findings:
        return text, []

    sanitized = text
    for item in sorted(findings, key=lambda x: x["start"], reverse=True):
        placeholder = f"[{item['type'].upper()}_REDACTED]"
        sanitized = sanitized[:item["start"]] + placeholder + sanitized[item["end"]:]
    return sanitized, findings
