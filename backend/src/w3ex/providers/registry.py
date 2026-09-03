from __future__ import annotations

from collections.abc import Callable
from typing import Any

ProviderFactory = Callable[[], Any]

_FACTORIES: dict[str, dict[str, ProviderFactory]] = {}


def register(component: str, name: str, factory: ProviderFactory) -> None:
    _FACTORIES.setdefault(component, {})[name] = factory


def build(component: str, env: str) -> Any:
    providers = _FACTORIES.get(component, {})
    if env not in providers:
        raise KeyError(f"No provider registered for {component!r}={env!r}")
    return providers[env]()


def available(component: str) -> list[str]:
    return sorted(_FACTORIES.get(component, {}).keys())
