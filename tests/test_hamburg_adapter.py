import json

import httpx

from custom_components.libbry_libs.adapters import hamburg as hamburg_module
from custom_components.libbry_libs.api import Library
from custom_components.libbry_libs.models import Loan, ProfileInfo, Reservation


class HamburgMockAPI:
    def __init__(self):
        self.login_calls = 0
        self.item_calls: dict[str, int] = {}
        self.force_unauthorized_once: set[str] = set()
        self.force_non_json_once: set[str] = set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user/login" and request.method == "POST":
            self.login_calls += 1
            payload = {
                "ok": True,
                "user": {
                    "userID": "A12345",
                    "userName": "Ada Lovelace",
                    "emailAddress": "ada@example.org",
                },
                "token": "token-value",
            }
            return httpx.Response(
                200,
                text=f"1:{json.dumps(payload)}",
                headers=[
                    ("set-cookie", "luci_session=session123; Path=/; Secure"),
                    ("set-cookie", "luci_token=token123; Path=/; Secure"),
                ],
            )

        if request.url.path == "/api/items" and request.method == "GET":
            assert request.headers.get("solus-app-id") == hamburg_module.HAMBURG_APP_ID
            item_type = request.url.params.get("type")
            self.item_calls[item_type] = self.item_calls.get(item_type, 0) + 1

            if (
                item_type in self.force_non_json_once
                and self.item_calls[item_type] == 1
            ):
                return httpx.Response(200, text="<!DOCTYPE html><html>not json</html>")

            if (
                item_type in self.force_unauthorized_once
                and self.item_calls[item_type] == 1
            ):
                return httpx.Response(403, text="forbidden")

            if item_type == "membership":
                return httpx.Response(
                    200,
                    json={
                        "currentMembership": {
                            "startDate": "2025-09-01",
                        }
                    },
                )
            if item_type == "loans":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "title": "The Calculating Engine",
                            "subtitle": "Origins",
                            "author": "Ada Lovelace",
                            "status": "Borrowed",
                            "canRenew": True,
                            "dueObject": "2025-12-31T00:00:00Z",
                            "imageUrl": "https://img.example.org/loan.jpg",
                        }
                    ],
                )
            if item_type == "holds":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "title": "Compiler Design",
                            "author": "Grace Hopper",
                            "status": "On hold",
                            "numberInQueue": 2,
                            "pickupDeadline": "2025-11-30",
                            "imageUrl2": "https://img.example.org/hold.jpg",
                        }
                    ],
                )
            if item_type == "charges":
                return httpx.Response(200, json={"charges": [], "chargePaymentUrl": ""})

        return httpx.Response(404, text="not found")


def _mock_hamburg_client(monkeypatch, api: HamburgMockAPI) -> None:
    original_async_client = httpx.AsyncClient

    mock_client_factory = lambda *_args, **_kwargs: original_async_client(
        transport=httpx.MockTransport(api)
    )
    monkeypatch.setattr(
        hamburg_module,
        "create_async_httpx_client",
        mock_client_factory,
    )
    monkeypatch.setattr(hamburg_module.httpx, "AsyncClient", mock_client_factory)


async def test_hamburg_profile_and_loans_mapping(monkeypatch):
    api = HamburgMockAPI()
    _mock_hamburg_client(monkeypatch, api)
    lib = Library("hamburg buecherhallen", "user", "1234")

    try:
        profile = await lib.get_profile_info()
        loans = await lib.get_loans()
    finally:
        await lib.session.aclose()

    assert isinstance(profile, ProfileInfo)
    assert profile.patron_id == "A12345"
    assert profile.name == "Ada Lovelace"
    assert profile.email_address == "ada@example.org"
    assert profile.birth_date.isoformat() == "2025-09-01"

    assert len(loans) == 1
    assert isinstance(loans[0], Loan)
    assert loans[0].title == "The Calculating Engine Origins"
    assert loans[0].author == "Ada Lovelace"
    assert loans[0].is_renewable is True
    assert loans[0].due_date.isoformat() == "2025-12-31"
    assert loans[0].image_url == "https://img.example.org/loan.jpg"
    assert api.login_calls == 1


async def test_hamburg_reservations_and_fees(monkeypatch):
    api = HamburgMockAPI()
    _mock_hamburg_client(monkeypatch, api)
    lib = Library("hamburg buecherhallen", "user", "1234")

    try:
        reservations = await lib.get_reservations()
        fees = await lib.get_fees()
    finally:
        await lib.session.aclose()

    assert len(reservations) == 1
    assert isinstance(reservations[0], Reservation)
    assert reservations[0].title == "Compiler Design"
    assert reservations[0].author == "Grace Hopper"
    assert reservations[0].number_in_queue == 2
    assert reservations[0].pickup_deadline.isoformat() == "2025-11-30"
    assert reservations[0].image_url == "https://img.example.org/hold.jpg"

    assert isinstance(fees, dict)
    assert fees["charges"] == []


async def test_hamburg_ereolen_calls_return_empty_lists(monkeypatch):
    api = HamburgMockAPI()
    _mock_hamburg_client(monkeypatch, api)
    lib = Library("hamburg buecherhallen", "user", "1234")

    ereolen_loans = await lib.get_ereolen_loans()
    ereolen_reservations = await lib.get_ereolen_reservations()

    assert ereolen_loans == []
    assert ereolen_reservations == []


async def test_hamburg_reauth_on_403(monkeypatch):
    api = HamburgMockAPI()
    api.force_unauthorized_once.add("loans")
    _mock_hamburg_client(monkeypatch, api)
    lib = Library("hamburg buecherhallen", "user", "1234")

    try:
        loans = await lib.get_loans()
    finally:
        await lib.session.aclose()

    assert len(loans) == 1
    assert api.login_calls == 2
    assert api.item_calls["loans"] == 2


async def test_hamburg_reauth_on_non_json_response(monkeypatch):
    api = HamburgMockAPI()
    api.force_non_json_once.add("loans")
    _mock_hamburg_client(monkeypatch, api)
    lib = Library("hamburg buecherhallen", "user", "1234")

    try:
        loans = await lib.get_loans()
    finally:
        await lib.session.aclose()

    assert len(loans) == 1
    assert api.login_calls == 2
    assert api.item_calls["loans"] == 2
