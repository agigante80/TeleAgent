# Pluggable History Storage

> Status: **Planned** | Priority: Low (long-term architecture)

## Problem

`history.py` is hardcoded to SQLite/aiosqlite. No abstraction exists for alternate storage backends (Postgres, Redis, flat file). All callers in `bot.py` reference `ConversationHistory` directly.

## Proposed Design

Introduce a `ConversationStorage` ABC:

```python
from abc import ABC, abstractmethod

class ConversationStorage(ABC):
    @abstractmethod
    async def add_exchange(self, chat_id: str, user: str, assistant: str) -> None: ...
    @abstractmethod
    async def get_history(self, chat_id: str, limit: int = 10) -> list[dict]: ...
    @abstractmethod
    async def clear(self, chat_id: str) -> None: ...
```

`SQLiteStorage` becomes the default implementation, instantiated in `main.py` via a factory. Callers receive the abstract type — zero changes to `bot.py` business logic.

## Files to Change

- `src/history.py` — extract ABC, keep `SQLiteStorage` as default
- `src/main.py` — construct storage via factory
- `tests/` — add contract test verifying `SQLiteStorage` satisfies ABC
