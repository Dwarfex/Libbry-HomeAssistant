import asyncio
import os

from custom_components.libbry_libs.api import Library


async def _run() -> None:
    user_id = os.environ.get("HAMBURG_USER_ID", "").strip()
    pin = os.environ.get("HAMBURG_PIN", "").strip()

    if not user_id or not pin:
        raise ValueError("HAMBURG_USER_ID und HAMBURG_PIN müssen gesetzt sein")

    library = Library("hamburg buecherhallen", user_id, pin)
    try:
        profile = await library.get_profile_info()
        loans = await library.get_loans()
        reservations = await library.get_reservations()
        fees = await library.get_fees()
    finally:
        if library.session is not None:
            await library.session.aclose()

    print("Hamburg Live-Check erfolgreich")
    print(f"Nutzer: {profile.name} ({profile.patron_id})")
    print(f"Ausleihen: {len(loans)}")
    print(f"Vormerkungen: {len(reservations)}")
    print(f"Gebührenstruktur: {type(fees).__name__}")


if __name__ == "__main__":
    asyncio.run(_run())
