from abc import ABC, abstractmethod
from typing import Any


class LibraryAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def authenticate(self, library) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def get_profile_info(self, library):
        raise NotImplementedError()

    @abstractmethod
    async def get_fees(self, library):
        raise NotImplementedError()

    @abstractmethod
    async def get_loans(self, library):
        raise NotImplementedError()

    @abstractmethod
    async def get_ereolen_loans(self, library):
        raise NotImplementedError()

    @abstractmethod
    async def get_reservations(self, library):
        raise NotImplementedError()

    @abstractmethod
    async def get_ereolen_reservations(self, library):
        raise NotImplementedError()

    @staticmethod
    def get_nested_value(data: dict[str, Any], keys: list[str]) -> Any:
        next_key = keys.pop(0)
        value = data[next_key]
        if len(keys) == 0 or value is None:
            return value
        return LibraryAdapter.get_nested_value(value, keys)


class AdapterRegistry:
    _registry: dict[str, type[LibraryAdapter]] = {}

    @classmethod
    def register(cls, adapter_class: type[LibraryAdapter]) -> type[LibraryAdapter]:
        cls._registry[adapter_class().name] = adapter_class
        return adapter_class

    @classmethod
    def get(cls, adapter_name: str) -> type[LibraryAdapter] | None:
        return cls._registry.get(adapter_name)

    @classmethod
    def create(cls, adapter_name: str) -> LibraryAdapter:
        adapter_class = cls.get(adapter_name)
        if adapter_class is None:
            raise ValueError(f'Adapter "{adapter_name}" not found in adapter registry')
        return adapter_class()

    @classmethod
    def registered_adapter_names(cls) -> list[str]:
        return sorted(cls._registry.keys())
