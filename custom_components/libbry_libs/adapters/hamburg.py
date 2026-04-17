from .base import AdapterRegistry, LibraryAdapter


@AdapterRegistry.register
class HamburgLibraryAdapter(LibraryAdapter):
    @property
    def name(self) -> str:
        return "hamburg"

    async def authenticate(self, library) -> None:
        raise NotImplementedError("Hamburg adapter authentication is not implemented")

    async def get_profile_info(self, library):
        raise NotImplementedError("Hamburg adapter profile API is not implemented")

    async def get_fees(self, library):
        raise NotImplementedError("Hamburg adapter fees API is not implemented")

    async def get_loans(self, library):
        raise NotImplementedError("Hamburg adapter loans API is not implemented")

    async def get_ereolen_loans(self, library):
        raise NotImplementedError(
            "Hamburg adapter eReolen loans API is not implemented"
        )

    async def get_reservations(self, library):
        raise NotImplementedError("Hamburg adapter reservations API is not implemented")

    async def get_ereolen_reservations(self, library):
        raise NotImplementedError(
            "Hamburg adapter eReolen reservations API is not implemented"
        )
