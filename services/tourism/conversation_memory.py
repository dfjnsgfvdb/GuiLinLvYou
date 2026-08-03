import json
import logging
import os
from datetime import datetime
from typing import Any

from common.redis_tool import RedisTool

logger = logging.getLogger(__name__)


class TourismConversationMemory:
    """Short-term Redis memory for tourism QA conversations."""

    def __init__(self):
        self.ttl_seconds = int(os.getenv("REDIS_CHAT_MEMORY_TTL_SECONDS", "1800"))
        self.max_turns = int(os.getenv("REDIS_CHAT_MEMORY_MAX_TURNS", "6"))
        self.enabled = os.getenv("REDIS_CHAT_MEMORY_ENABLED", "true").lower() == "true"
        self.redis = RedisTool() if self.enabled else None

    def load(self, user_id: str | int, chat_id: str | None) -> list[dict[str, Any]]:
        if not self.enabled or not chat_id:
            return []
        try:
            payload = self.redis.get_key(self._key(user_id, chat_id))
            if not payload:
                return []
            turns = json.loads(payload)
            return turns if isinstance(turns, list) else []
        except Exception as exc:
            logger.warning("读取 Redis 短期对话记忆失败: %s", exc, exc_info=True)
            return []

    def append_turn(self, user_id: str | int, chat_id: str | None, question: str, answer: str) -> None:
        if not self.enabled or not chat_id:
            return
        try:
            turns = self.load(user_id, chat_id)
            turns.append(
                {
                    "question": question,
                    "answer": answer,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            turns = turns[-self.max_turns :]
            self.redis.set_key(self._key(user_id, chat_id), json.dumps(turns, ensure_ascii=False), ex=self.ttl_seconds)
        except Exception as exc:
            logger.warning("写入 Redis 短期对话记忆失败: %s", exc, exc_info=True)

    @staticmethod
    def compact_for_prompt(turns: list[dict[str, Any]], max_chars: int = 1800) -> str:
        if not turns:
            return "无"
        lines = []
        for index, turn in enumerate(turns, 1):
            lines.append(f"{index}. 用户：{turn.get('question', '')}")
            lines.append(f"   助手：{turn.get('answer', '')[:300]}")
        text = "\n".join(lines)
        return text[-max_chars:] if len(text) > max_chars else text

    @staticmethod
    def _key(user_id: str | int, chat_id: str) -> str:
        return f"tourism:qa:memory:{user_id}:{chat_id}"
