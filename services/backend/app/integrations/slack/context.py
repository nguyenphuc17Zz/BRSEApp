from typing import Dict, List, Any, Optional
from app.integrations.slack.client import SlackClient

class SlackContextRetriever:
    """Retrieves and formats chronological Slack thread context and nearby conversation history."""

    @classmethod
    async def build_message_context(
        cls,
        token: str,
        channel_id: str,
        channel_name: str,
        message_ts: str,
        thread_ts: Optional[str] = None,
        is_mock: bool = False
    ) -> Dict[str, Any]:
        """Gathers thread context or nearby messages around the selected message."""
        context_messages: List[Dict[str, str]] = []

        if thread_ts:
            # Message is inside a thread -> Fetch thread replies
            raw_thread = await SlackClient.get_thread_replies(token, channel_id, thread_ts, is_mock=is_mock)
            for m in raw_thread:
                sender = m.get("username") or m.get("user", "Unknown")
                text = m.get("text", "")
                ts = m.get("ts", "")
                context_messages.append({
                    "sender": sender,
                    "text": text,
                    "is_current": ts == message_ts
                })
        else:
            # Standalone message -> Fetch nearby channel messages
            channel_msgs = await SlackClient.get_channel_history(token, channel_id, limit=10, is_mock=is_mock)
            # Reverse to maintain chronological order
            for m in reversed(channel_msgs):
                sender = m.get("username") or m.get("user", "Unknown")
                text = m.get("text", "")
                ts = m.get("ts", "")
                context_messages.append({
                    "sender": sender,
                    "text": text,
                    "is_current": ts == message_ts
                })

        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "thread_ts": thread_ts,
            "messages": context_messages,
            "thread_length": len(context_messages)
        }
