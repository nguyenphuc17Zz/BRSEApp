import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, List, Optional
import httpx
from app.core.logging import logger
from app.core.config import settings

class LineClient:
    """Legitimate LINE Messaging API integration.
    Supports official Bot / Webhook events, message normalization, and explicit user-confirmed replies.
    No scraping of personal accounts.
    """

    def __init__(self, channel_access_token: Optional[str] = None, channel_secret: Optional[str] = None):
        self.channel_access_token = channel_access_token or getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", "")
        self.channel_secret = channel_secret or getattr(settings, "LINE_CHANNEL_SECRET", "")
        self.api_base = "https://api.line.me/v2/bot"

    def verify_signature(self, body_bytes: bytes, signature: str) -> bool:
        """Verifies LINE Webhook HMAC-SHA256 signature."""
        if not self.channel_secret:
            return True # Dev/mock mode when secret is not configured
        hash_val = hmac.new(self.channel_secret.encode("utf-8"), body_bytes, hashlib.sha256).digest()
        expected_sig = base64.b64encode(hash_val).decode("utf-8")
        return hmac.compare_digest(expected_sig, signature)

    def normalize_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalizes a single LINE webhook event into standard Unified Message Model."""
        if event.get("type") != "message":
            return None
        
        msg = event.get("message", {})
        if msg.get("type") != "text":
            return None # We currently prioritize text messages

        source = event.get("source", {})
        sender_id = source.get("userId") or source.get("groupId") or source.get("roomId") or "unknown_user"
        conv_id = source.get("groupId") or source.get("roomId") or sender_id
        
        ts_ms = event.get("timestamp", int(time.time() * 1000))
        # Format timestamp to ISO
        ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_ms / 1000.0))

        return {
            "source": "line",
            "conversation_id": conv_id,
            "message_id": msg.get("id", f"line-msg-{int(time.time())}"),
            "sender": sender_id,
            "timestamp": ts_iso,
            "text": msg.get("text", ""),
            "reply_token": event.get("replyToken"),
            "reply_to": None
        }

    def parse_webhook_payload(self, body: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parses webhook payload containing multiple events."""
        events = body.get("events", [])
        normalized = []
        for event in events:
            norm = self.normalize_event(event)
            if norm:
                normalized.append(norm)
        return normalized

    async def send_reply_message(self, reply_token: str, text: str) -> Dict[str, Any]:
        """Sends a reply using LINE Messaging API.
        NOTE: Must ONLY be called upon explicit user confirmation from UI!
        """
        if not self.channel_access_token:
            logger.info(f"[MOCK LINE REPLY] Token={reply_token}, Text={text}")
            return {"status": "mock_sent", "message": "LINE message simulated (No token provided)"}

        url = f"{self.api_base}/message/reply"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}"
        }
        payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": text
                }
            ]
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                logger.error(f"LINE reply failed: {resp.status_code} {resp.text}")
                raise RuntimeError(f"LINE API Error ({resp.status_code}): {resp.text}")
            return {"status": "sent", "response": resp.json() if resp.text else {}}

line_client = LineClient()
