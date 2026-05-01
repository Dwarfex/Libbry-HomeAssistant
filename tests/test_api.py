import asyncio
import os

import dotenv
import pytest

from custom_components.libbry_libs.api import Library
from custom_components.libbry_libs.models import (
    BaseLoan,
    BaseReservation,
    EreolenLoan,
    EreolenReservation,
    Loan,
    ProfileInfo,
    Reservation,
)

dotenv.load_dotenv()

LIBRARY_USER_ID = os.getenv("LIBRARY_USER_ID")
LIBRARY_PIN = os.getenv("LIBRARY_PIN")
MUNICIPALITY = os.getenv("MUNICIPALITY")

if not all([LIBRARY_USER_ID, LIBRARY_PIN, MUNICIPALITY]):
    pytestmark = pytest.mark.skip(
        reason="Integration credentials are not configured "
        "(LIBRARY_USER_ID, LIBRARY_PIN, MUNICIPALITY)"
    )


def test_default_adapter_is_denmark():
    lib = Library("albertslund", "user", "1234")
    assert lib.adapter.name == "denmark"


def test_library_can_resolve_hamburg_adapter_from_config():
    lib = Library("hamburg buecherhallen", "user", "1234")
    assert lib.adapter.name == "hamburg"


def test_unknown_adapter_raises_value_error():
    with pytest.raises(ValueError):
        Library("albertslund", "user", "1234", adapter_name="unknown")


def test_hamburg_adapter_exposes_library_contract_methods():
    lib = Library("hamburg buecherhallen", "user", "1234")
    assert callable(lib.adapter.authenticate)
    assert callable(lib.adapter.get_profile_info)
    assert callable(lib.adapter.get_loans)
    assert callable(lib.adapter.get_reservations)
    assert callable(lib.adapter.get_fees)
    assert callable(lib.adapter.get_ereolen_loans)
    assert callable(lib.adapter.get_ereolen_reservations)


async def test_auth():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    await lib.authenticate()
    assert lib.user_bearer_token is not None


async def test_loans():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    loans = await lib.get_loans()
    assert loans is not None
    assert len(loans) > 0
    assert isinstance(loans[0], Loan)
    assert isinstance(loans[0], BaseLoan)


async def test_reservations():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    reservations = await lib.get_reservations()
    assert reservations is not None
    assert len(reservations) > 0
    assert isinstance(reservations[0], Reservation)
    assert isinstance(reservations[0], BaseReservation)


async def test_profile():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    profile = await lib.get_profile_info()
    assert profile is not None
    assert isinstance(profile, ProfileInfo)
    assert "gmail.com" in profile.email_address


async def test_ereolen_loans():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    loans = await lib.get_ereolen_loans()
    assert loans is not None
    assert len(loans) > 0
    assert isinstance(loans[0], EreolenLoan)
    assert isinstance(loans[0], BaseLoan)


async def test_ereolen_reservations():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    reservations = await lib.get_ereolen_reservations()
    assert reservations is not None
    assert len(reservations) > 0
    assert isinstance(reservations[0], EreolenReservation)
    assert isinstance(reservations[0], BaseReservation)
