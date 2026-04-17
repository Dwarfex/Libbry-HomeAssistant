import asyncio
from typing import Any

from .adapters import AdapterRegistry
from .const import LIBRARIES, LOGGER


class Library:
    # pylint: disable=too-many-instance-attributes
    def __init__(
        self,
        municipality: str,
        user_id: str,
        pin: str,
        hass=None,
        adapter_name: str | None = None,
    ):
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        municipality_key = municipality.lower()
        if municipality_key not in LIBRARIES.keys():
            raise ValueError(f'Municipality "{municipality}" not found in list')
        self.municipality = LIBRARIES[municipality_key]
        self.adapter = AdapterRegistry.create(adapter_name or self.municipality.adapter)
        self.user_id = user_id
        self.pin = pin
        self.session = None
        self.user_token = None
        self.library_token = None
        self.hass = hass

    @property
    def user_bearer_token(self):
        return f"Bearer {self.user_token}"

    @property
    def library_bearer_token(self):
        return f"Bearer {self.library_token}"

    async def authenticate(self):
        await self.adapter.authenticate(self)

    async def get_profile_info(self):
        return await self.adapter.get_profile_info(self)

    async def get_fees(self):
        return await self.adapter.get_fees(self)

    async def get_loans(self):
        return await self.adapter.get_loans(self)

    async def get_ereolen_loans(self):
        return await self.adapter.get_ereolen_loans(self)

    async def get_reservations(self):
        return await self.adapter.get_reservations(self)

    async def get_ereolen_reservations(self):
        return await self.adapter.get_ereolen_reservations(self)

    async def unpack_results(self, tasks):
        if len(tasks) == 0:
            return []
        done, _ = await asyncio.wait(tasks, return_when="ALL_COMPLETED")
        for x in done:
            if ex := x.exception():
                LOGGER.exception(ex)
        return [x.result() for x in done]

    @staticmethod
    def get_nested_value(d: dict[str, Any], keys: list[str]) -> Any:
        next_key = keys.pop(0)
        value = d[next_key]
        if len(keys) == 0 or value is None:
            return value
        return Library.get_nested_value(value, keys)
