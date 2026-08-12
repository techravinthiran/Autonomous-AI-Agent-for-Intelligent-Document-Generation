"""
Conversation Memory – Engineering Improvement #1
Stores per-session message history so the agent can reference prior context
when the same session_id is reused across multiple requests.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict

MEMORY_DIR = Path("memory_store")
MEMORY_DIR.mkdir(exist_ok=True)


class ConversationMemory:
    """
    Simple file-backed conversation memory.

    Why this matters:
    - Allows multi-turn refinement: "make it shorter" knows what "it" is.
    - Provides LLM with prior assumptions so it doesn't contradict itself.
    - Lightweight – no vector DB needed for session-scoped context.
    """

    def __init__(self, session_id: str, max_messages: int = 20):
        self.session_id = session_id
        self.max_messages = max_messages
        self._filepath = MEMORY_DIR / f"{session_id}.json"
        self._messages: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        if self._filepath.exists():
            try:
                with open(self._filepath, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save(self):
        with open(self._filepath, "w") as f:
            json.dump(self._messages, f, indent=2)

    def add_user_message(self, content: str):
        self._messages.append({
            "role": "user",
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        # Keep within limit
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]
        self._save()

    def add_assistant_message(self, content: str):
        self._messages.append({
            "role": "assistant",
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages:]
        self._save()

    def get_history(self) -> List[Dict]:
        return list(self._messages)

    def get_llm_messages(self) -> List[Dict]:
        """Return messages in OpenAI/Groq format (role + content only)."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in self._messages
        ]

    def get_context_summary(self) -> str:
        """Produce a compact text summary of prior turns for prompt injection."""
        if len(self._messages) <= 1:
            return "No prior conversation context."
        lines = ["Prior conversation context:"]
        for m in self._messages[:-1]:  # exclude current message
            role = "User" if m["role"] == "user" else "Assistant"
            snippet = m["content"][:150].replace("\n", " ")
            lines.append(f"  [{role}]: {snippet}")
        return "\n".join(lines)

    def clear(self):
        self._messages = []
        if self._filepath.exists():
            self._filepath.unlink()
