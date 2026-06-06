from __future__ import annotations

from typing import TYPE_CHECKING

from dodoo.core.exceptions import DodooError

if TYPE_CHECKING:
    from dodoo.core.models import BaseModel


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, type[BaseModel]] = {}
        self._inheritance: dict[str, str] = {}  # child_name -> parent_name

    def register(self, cls: type[BaseModel]) -> None:
        name = cls._name
        if name in self._models:
            raise DodooError(f"Model '{name}' is already registered")
        self._models[name] = cls

        parent = getattr(cls, "_inherit", None)
        if parent:
            self._inheritance[name] = parent

    def lookup(self, name: str) -> type[BaseModel]:
        try:
            return self._models[name]
        except KeyError:
            raise DodooError(f"Model '{name}' is not registered") from None

    def all_models(self) -> list[type[BaseModel]]:
        return list(self._models.values())

    def parent_of(self, name: str) -> str | None:
        return self._inheritance.get(name)

    def is_child(self, name: str) -> bool:
        return name in self._inheritance
