"""Lightweight extension registries for AgentGate subsystems.

Each registry maps a string key to a factory callable.
Registrations happen at import time via the ``@registry.register(key)`` decorator.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class Registry:
    """Maps string keys to factory callables."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._map: dict[str, Callable] = {}

    def register(self, key: str, *, force: bool = False) -> Callable:
        """Decorator — register a class or factory function under *key*.

        Raises ``ValueError`` on duplicate keys unless *force=True* is passed explicitly.
        ``force=True`` is for intentional overrides in fork compositions; never use it in
        core modules.
        """
        def decorator(cls_or_fn: Callable) -> Callable:
            if key in self._map:
                if not force:
                    raise ValueError(
                        f"Registry {self._name!r}: key {key!r} already registered by "
                        f"{self._map[key]!r}. Use force=True to override intentionally."
                    )
                logger.warning(
                    "Registry %r: key %r overwritten (force=True). "
                    "Previous: %r  New: %r",
                    self._name, key, self._map[key], cls_or_fn,
                )
            self._map[key] = cls_or_fn
            return cls_or_fn
        return decorator

    def create(self, key: str, *args: Any, **kwargs: Any) -> Any:
        """Instantiate the registered factory for *key*."""
        if key not in self._map:
            available = ", ".join(sorted(self._map))
            raise ValueError(
                f"{self._name}: unknown key {key!r}. Available: {available or '(none)'}"
            )
        return self._map[key](*args, **kwargs)

    def keys(self) -> list[str]:
        return list(self._map)

    def __contains__(self, key: str) -> bool:
        return key in self._map


backend_registry:  Registry = Registry("AI backend")
platform_registry: Registry = Registry("Platform")
storage_registry:  Registry = Registry("Storage")
audit_registry:    Registry = Registry("Audit")
