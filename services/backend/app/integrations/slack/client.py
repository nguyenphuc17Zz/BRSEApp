from typing import Dict, List, Any, Optional
import httpx
from app.core.logging import logger

SLACK_API_BASE = "https://slack.com/api"

MOCK_SLACK_CHANNELS = [
    {"id": "C01ABCDEF", "name": "project-abc-banking", "is_private": False, "topic": "ABC Banking Project Communication"},
    {"id": "C02XYZWUV", "name": "bug-reports", "is_private": False, "topic": "QA and Issue Tracking"},
    {"id": "C03LEADS", "name": "brse-client-meeting", "is_private": True, "topic": "Direct client discussions"}
]

MOCK_SLACK_MESSAGES = {
    "C01ABCDEF": [
        {
            "ts": "1725440000.000100",
            "user": "U_YAMADA",
            "username": "Yamada (PM)",
            "text": "おはようございます。本日のリリース手順について確認させてください。",
            "reply_count": 2,
            "thread_ts": "1725440000.000100"
        },
        {
            "ts": "1725440050.000200",
            "user": "U_SUZUKI",
            "username": "Suzuki (Tech Lead)",
            "text": "API側でOAuthトークンの失効処理を修正しました。ステージング環境でテスト可能です。",
            "thread_ts": "1725440000.000100"
        },
        {
            "ts": "1725440100.000300",
            "user": "U_YAMADA",
            "username": "Yamada (PM)",
            "text": "ありがとうございます。ベトナムチーム側での結合テストはいつ頃完了予定でしょうか？",
            "thread_ts": "1725440000.000100"
        }
    ],
    "C02XYZWUV": [
        {
            "ts": "1725441000.000100",
            "user": "U_TANAKA",
            "username": "Tanaka (QA)",
            "text": "【至急バグ報告】ログイン画面でパスワードに特殊文字を含めると500エラーが発生します。調査をお願いできますか？",
            "reply_count": 0
        }
    ]
}

class SlackClient:
    """Manages Slack OAuth, channel listing, message and thread history retrieval."""

    @classmethod
    def get_auth_url(cls, client_id: str, redirect_uri: str, state: str = "slack_auth") -> str:
        scopes = "channels:read,groups:read,channels:history,groups:history,im:history,mpim:history,users:read"
        return f"https://slack.com/oauth/v2/authorize?client_id={client_id}&scope={scopes}&redirect_uri={redirect_uri}&state={state}"

    @classmethod
    async def exchange_code(cls, code: str, client_id: str, client_secret: str, redirect_uri: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                f"{SLACK_API_BASE}/oauth.v2.access",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri
                }
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Slack OAuth failed: {data}")
                raise ValueError(f"Slack OAuth error: {data.get('error')}")
            return data

    @classmethod
    async def list_channels(cls, token: str, is_mock: bool = False) -> List[Dict[str, Any]]:
        """Lists public and private channels accessible to the user/bot."""
        if is_mock or token.startswith("mock_"):
            return MOCK_SLACK_CHANNELS

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                f"{SLACK_API_BASE}/conversations.list?types=public_channel,private_channel,im,mpim",
                headers=headers
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Failed to list Slack channels: {data.get('error')}")
                return []
            return [
                {
                    "id": c["id"],
                    "name": c.get("name", c["id"]),
                    "is_private": c.get("is_private", False),
                    "topic": c.get("topic", {}).get("value", "")
                }
                for c in data.get("channels", [])
            ]

    @classmethod
    async def get_channel_history(cls, token: str, channel_id: str, limit: int = 30, is_mock: bool = False) -> List[Dict[str, Any]]:
        """Retrieves recent messages from a channel."""
        if is_mock or token.startswith("mock_"):
            return MOCK_SLACK_MESSAGES.get(channel_id, [])

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                f"{SLACK_API_BASE}/conversations.history?channel={channel_id}&limit={limit}",
                headers=headers
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Failed to fetch Slack history for {channel_id}: {data.get('error')}")
                return []
            return data.get("messages", [])

    @classmethod
    async def get_thread_replies(cls, token: str, channel_id: str, thread_ts: str, is_mock: bool = False) -> List[Dict[str, Any]]:
        """Retrieves all replies in a specific message thread."""
        if is_mock or token.startswith("mock_"):
            # Return mock thread messages
            msgs = MOCK_SLACK_MESSAGES.get(channel_id, [])
            return [m for m in msgs if m.get("thread_ts") == thread_ts or m.get("ts") == thread_ts]

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.get(
                f"{SLACK_API_BASE}/conversations.replies?channel={channel_id}&ts={thread_ts}",
                headers=headers
            )
            data = resp.json()
            if not data.get("ok"):
                logger.error(f"Failed to fetch thread replies for {thread_ts}: {data.get('error')}")
                return []
            return data.get("messages", [])
