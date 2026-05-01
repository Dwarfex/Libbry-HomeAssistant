import json
from collections.abc import Mapping
from datetime import date
from typing import Any

try:
    # pylint: disable=invalid-name
    from homeassistant.helpers.httpx_client import create_async_httpx_client, httpx
except ImportError:
    import httpx

    create_async_httpx_client = httpx.AsyncClient

from ..const import LOGGER
from ..models import Loan, ProfileInfo, Reservation
from .base import AdapterRegistry, LibraryAdapter

HAMBURG_BASE_URL = "https://www2.buecherhallen.de"
HAMBURG_LOGIN_ENDPOINT = "/user/login"
HAMBURG_ITEMS_ENDPOINT = "/api/items"
HAMBURG_APP_ID = "BUECHERHALLEN"
HAMBURG_LOGIN_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": HAMBURG_BASE_URL,
    "Referer": f"{HAMBURG_BASE_URL}/login",
}
HAMBURG_LOGIN_TIMEOUT = 30
HAMBURG_API_TIMEOUT = 30
AUTH_COOKIE_KEYS = ("luci_session", "luci_token")


@AdapterRegistry.register
class HamburgLibraryAdapter(LibraryAdapter):
    def __init__(self) -> None:
        self._patron_data: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "hamburg"

    async def authenticate(self, library) -> None:
        await self._ensure_session(library)
        library.session.cookies.clear()
        payload = [
            {
                "userID": library.user_id,
                "password": library.pin,
                "hvToken": "",
                "keepIn": False,
            },
            False,
        ]
        response = await library.session.post(
            f"{HAMBURG_BASE_URL}{HAMBURG_LOGIN_ENDPOINT}",
            headers=HAMBURG_LOGIN_HEADERS,
            json=payload,
            timeout=HAMBURG_LOGIN_TIMEOUT,
        )
        response.raise_for_status()
        response_payload = self._parse_json_response(response)
        if not isinstance(response_payload, Mapping):
            raise ValueError("Unexpected Hamburg login response payload")
        if not response_payload.get("ok"):
            raise ValueError(response_payload.get("message") or "Hamburg login failed")

        missing_cookies = [
            cookie_name
            for cookie_name in AUTH_COOKIE_KEYS
            if library.session.cookies.get(cookie_name) is None
        ]
        if missing_cookies:
            LOGGER.warning(
                "Hamburg login succeeded without expected cookies: %s", missing_cookies
            )

        self._patron_data = self._extract_patron_data(response_payload)

    async def get_profile_info(self, library):
        if not self._patron_data:
            await self.authenticate(library)

        membership_payload = await self._authenticated_api_get(library, "membership")
        return ProfileInfo(
            self._normalize_profile_payload(self._patron_data, membership_payload)
        )

    async def get_fees(self, library):
        return await self._authenticated_api_get(library, "charges")

    async def get_loans(self, library):
        loans_payload = await self._authenticated_api_get(library, "loans")
        if not isinstance(loans_payload, list):
            LOGGER.warning(
                "Unexpected Hamburg loans payload: %s", type(loans_payload).__name__
            )
            return []

        loans: list[Loan] = []
        for item in loans_payload:
            if not isinstance(item, Mapping):
                continue
            due_date = self._normalize_iso_date(item.get("dueObject"))
            if due_date is None:
                LOGGER.warning(
                    "Skipping Hamburg loan without parseable due date: %s", item
                )
                continue
            loan_data = {
                "isRenewable": bool(item.get("canRenew", False)),
                "loanDetails": {"dueDate": due_date},
            }
            lookup_data = self._build_lookup_data(item)
            loans.append(Loan(loan_data, lookup_data, self._select_image_url(item)))
        return loans

    async def get_ereolen_loans(self, library):
        return []

    async def get_reservations(self, library):
        holds_payload = await self._authenticated_api_get(library, "holds")
        if not isinstance(holds_payload, list):
            LOGGER.warning(
                "Unexpected Hamburg holds payload: %s", type(holds_payload).__name__
            )
            return []

        reservations: list[Reservation] = []
        for item in holds_payload:
            if not isinstance(item, Mapping):
                continue
            reservation_data = {
                "numberInQueue": int(
                    item.get("numberInQueue")
                    or item.get("queuePosition")
                    or item.get("position")
                    or 0
                ),
                "pickupDeadline": self._normalize_iso_date(item.get("pickupDeadline")),
            }
            lookup_data = self._build_lookup_data(item)
            reservations.append(
                Reservation(reservation_data, lookup_data, self._select_image_url(item))
            )
        return reservations

    async def get_ereolen_reservations(self, library):
        return []

    async def _ensure_session(self, library) -> None:
        if library.session is not None:
            return
        library.session = (
            create_async_httpx_client()
            if not library.hass
            else create_async_httpx_client(library.hass)
        )

    async def _authenticated_api_get(self, library, item_type: str) -> Any:
        if not self._has_auth_cookies(library):
            await self.authenticate(library)

        response = await library.session.get(
            f"{HAMBURG_BASE_URL}{HAMBURG_ITEMS_ENDPOINT}",
            params={"type": item_type},
            headers=self._build_api_headers(),
            timeout=HAMBURG_API_TIMEOUT,
        )

        if response.status_code in (401, 403):
            LOGGER.debug(
                "Hamburg %s request returned %s, re-authenticating",
                item_type,
                response.status_code,
            )
            await self.authenticate(library)
            response = await library.session.get(
                f"{HAMBURG_BASE_URL}{HAMBURG_ITEMS_ENDPOINT}",
                params={"type": item_type},
                headers=self._build_api_headers(),
                timeout=HAMBURG_API_TIMEOUT,
            )

        response.raise_for_status()
        return self._parse_json_response(response)

    @staticmethod
    def _build_api_headers() -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "solus-app-id": HAMBURG_APP_ID,
        }

    @staticmethod
    def _extract_patron_data(login_payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(login_payload, Mapping):
            return {}
        return dict(login_payload.get("user") or {})

    @staticmethod
    def _parse_json_response(response: httpx.Response) -> Any:
        response_text = response.text
        if response_text.startswith("1:"):
            response_text = response_text[2:]
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            LOGGER.warning(
                "Hamburg endpoint returned non-JSON response: %s", response_text[:300]
            )
            raise

    @staticmethod
    def _has_auth_cookies(library) -> bool:
        return all(
            library.session.cookies.get(cookie_name) for cookie_name in AUTH_COOKIE_KEYS
        )

    @staticmethod
    def _normalize_profile_payload(
        patron_payload: Mapping[str, Any], membership_payload: Any
    ) -> dict[str, str]:
        payload = membership_payload if isinstance(membership_payload, Mapping) else {}
        current_membership = payload.get("currentMembership")
        patron_data = patron_payload if isinstance(patron_payload, Mapping) else {}
        if isinstance(current_membership, Mapping):
            birthday = str(
                current_membership.get("startDate") or date.today().isoformat()
            )
        else:
            birthday = date.today().isoformat()

        full_name = str(
            patron_data.get("userName")
            or f"{patron_data.get('firstName', '')} {patron_data.get('lastName', '')}".strip()
        )

        return {
            "birthday": birthday,
            "emailAddress": str(patron_data.get("emailAddress") or ""),
            "name": full_name,
            "patronId": str(patron_data.get("userID") or ""),
        }

    @staticmethod
    def _build_lookup_data(item: Mapping[str, Any]) -> dict[str, Any]:
        title = str(item.get("title") or "")
        author = str(item.get("author") or "")
        subtitle = str(item.get("subtitle") or "")
        combined_title = title if not subtitle else f"{title} {subtitle}".strip()
        return {
            "creators": [{"display": author}] if author else [{"display": "Unknown"}],
            "titles": {"full": [combined_title or "Unknown"]},
            "abstract": [str(item.get("status") or item.get("format") or "")],
        }

    @staticmethod
    def _normalize_iso_date(value: Any) -> str | None:
        if value is None:
            return None
        text_value = str(value).strip()
        if not text_value:
            return None
        if "T" in text_value:
            text_value = text_value.split("T", maxsplit=1)[0]
        try:
            return date.fromisoformat(text_value).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _select_image_url(item: Mapping[str, Any]) -> str:
        return (
            str(item.get("imageUrl2") or "")
            or str(item.get("imageUrl") or "")
            or str(item.get("imageUrlLarge") or "")
        )
