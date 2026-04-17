from datetime import date
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BaseLoan(Protocol):
    author: str
    title: str
    image_url: str
    description: str
    due_date: date

    def to_json(self) -> dict[str, Any]: ...


@runtime_checkable
class BaseReservation(Protocol):
    author: str
    title: str
    image_url: str
    description: str

    def to_json(self) -> dict[str, Any]: ...
