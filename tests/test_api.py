
import asyncio
import os

import dotenv
import pytest

from custom_components.libbry_libs.api import Library
from custom_components.libbry_libs.models import (
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
        reason="Integration credentials are not configured (LIBRARY_USER_ID, LIBRARY_PIN, MUNICIPALITY)"
    )


async def test_auth():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    await lib.authenticate()
    assert lib.user_bearer_token != None


async def test_loans():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    loans = await lib.get_loans()
    assert loans != None
    assert len(loans) > 0
    assert isinstance(loans[0], Loan)


async def test_reservations():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    reservations = await lib.get_reservations()
    assert reservations != None
    assert len(reservations) > 0
    assert isinstance(reservations[0], Reservation)


async def test_profile():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    profile = await lib.get_profile_info()
    assert profile != None
    assert isinstance(profile, ProfileInfo)
    assert "gmail.com" in profile.email_address


async def test_ereolen_loans():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    loans = await lib.get_ereolen_loans()
    assert loans != None
    assert len(loans) > 0
    assert isinstance(loans[0], EreolenLoan)


async def test_ereolen_reservations():
    lib = Library(MUNICIPALITY, LIBRARY_USER_ID, LIBRARY_PIN)
    reservations = await lib.get_ereolen_reservations()
    assert reservations != None
    assert len(reservations) > 0
    assert isinstance(reservations[0], EreolenReservation)
