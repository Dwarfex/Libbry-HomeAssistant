import json
import re
from base64 import urlsafe_b64decode
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
HAMBURG_APP_ID = "28d4dc2f-692b-472b-870d-5e6c35c4ad26"
HAMBURG_LOGIN_HEADERS = {
    "Accept": "text/x-component",
    "Content-Type": "text/plain;charset=UTF-8",
    "Origin": HAMBURG_BASE_URL,
    "Referer": f"{HAMBURG_BASE_URL}{HAMBURG_LOGIN_ENDPOINT}",
    "User-Agent": (
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:150.0) "
        "Gecko/20100101 Firefox/150.0"
    ),
}
HAMBURG_PAGE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": f"{HAMBURG_BASE_URL}{HAMBURG_LOGIN_ENDPOINT}",
    "User-Agent": HAMBURG_LOGIN_HEADERS["User-Agent"],
}
HAMBURG_LOGIN_TIMEOUT = 30
HAMBURG_API_TIMEOUT = 30
AUTH_COOKIE_KEYS = ("luci_session", "luci_token")
HAMBURG_NEXT_ROUTER_STATE_TREE = (
    "%5B%22%22%2C%7B%22children%22%3A%5B%22user%22%2C%7B%22children%22%3A%5B%22login%22%2C"
    "%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2C"
    "null%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
)
NEXT_ACTION_PATTERN = re.compile(r"\b[a-f0-9]{40,42}\b")
LOGIN_PAGE_SCRIPT_PATTERN = re.compile(
    r'/_next/static/chunks/app/user/login/page-[^"]+\.js'
)


@AdapterRegistry.register
class HamburgLibraryAdapter(LibraryAdapter):
    def __init__(self) -> None:
        self._patron_data: dict[str, Any] = {}
        self._next_action: str | None = None

    @property
    def name(self) -> str:
        return "hamburg"

    async def authenticate(self, library) -> None:
        await self._ensure_session(library)
        next_action = await self._resolve_next_action(library)
        payload = [
            {
                "userID": library.user_id,
                "password": library.pin,
                "hvToken": "",
                "keepIn": False,
            },
            False,
        ]
        headers = dict(HAMBURG_LOGIN_HEADERS)
        if next_action:
            headers["next-action"] = next_action
        headers["next-router-state-tree"] = HAMBURG_NEXT_ROUTER_STATE_TREE

        response = await library.session.post(
            f"{HAMBURG_BASE_URL}{HAMBURG_LOGIN_ENDPOINT}",
            headers=headers,
            content=json.dumps(payload, separators=(",", ":")),
            timeout=HAMBURG_LOGIN_TIMEOUT,
        )
        response.raise_for_status()
        response_payload: Mapping[str, Any] | None = None
        try:
            parsed_response = self._parse_json_response(response)
            if isinstance(parsed_response, Mapping):
                response_payload = parsed_response
                if not response_payload.get("ok"):
                    raise ValueError(
                        response_payload.get("message") or "Hamburg login failed"
                    )
        except json.JSONDecodeError:
            LOGGER.debug(
                "Hamburg login returned non-JSON payload, checking auth cookies"
            )

        missing_cookies = [
            cookie_name
            for cookie_name in AUTH_COOKIE_KEYS
            if library.session.cookies.get(cookie_name) is None
        ]
        if missing_cookies:
            LOGGER.debug(
                "Hamburg login response status=%s content-type=%s body_prefix=%.200s",
                response.status_code,
                response.headers.get("content-type", "?"),
                response.text,
            )
            raise ValueError(
                f"Hamburg login missing expected auth cookies: {missing_cookies}. "
                "This may be caused by a Cloudflare Turnstile challenge blocking "
                "the programmatic login. The integration will work once Home Assistant "
                "is able to complete the challenge (e.g. when running on a trusted IP)."
            )

        self._patron_data = self._extract_patron_data(
            response_payload or self._extract_patron_data_from_session_cookie(library)
        )

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
        # Use HA's httpx client factory when hass is available — it initialises SSL
        # off the event loop, avoiding the "blocking call" warning. When running
        # outside HA (tests, CLI) create a plain AsyncClient directly.
        if library.hass is not None:
            try:
                library.session = create_async_httpx_client(
                    library.hass, follow_redirects=True
                )
                return
            except TypeError:
                library.session = create_async_httpx_client(library.hass)
                return
        library.session = httpx.AsyncClient(follow_redirects=True)

    async def _authenticated_api_get(self, library, item_type: str) -> Any:
        await self._ensure_session(library)
        if not self._has_auth_cookies(library):
            await self.authenticate(library)

        for attempt in range(2):
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
                continue

            response.raise_for_status()
            try:
                return self._parse_json_response(response)
            except json.JSONDecodeError:
                if attempt == 0:
                    LOGGER.debug(
                        "Hamburg %s request returned non-JSON payload, re-authenticating",
                        item_type,
                    )
                    await self.authenticate(library)
                    continue
                raise

        raise ValueError(
            f"Hamburg request for {item_type} failed after re-authentication"
        )

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
    def _extract_patron_data_from_session_cookie(library) -> dict[str, Any]:
        session_cookie = library.session.cookies.get("luci_session")
        if not session_cookie:
            return {}
        parts = session_cookie.split(".")
        if len(parts) < 2:
            return {}
        try:
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            decoded_payload = json.loads(urlsafe_b64decode(payload.encode()).decode())
        except (ValueError, TypeError):
            return {}
        patron = decoded_payload.get("patron")
        return dict(patron) if isinstance(patron, Mapping) else {}

    async def _resolve_next_action(self, library) -> str | None:
        if self._next_action:
            return self._next_action

        try:
            page_response = await library.session.get(
                f"{HAMBURG_BASE_URL}{HAMBURG_LOGIN_ENDPOINT}",
                headers=HAMBURG_PAGE_HEADERS,
                timeout=HAMBURG_LOGIN_TIMEOUT,
            )
            page_response.raise_for_status()

            script_match = LOGIN_PAGE_SCRIPT_PATTERN.search(page_response.text)
            if not script_match:
                raise ValueError("Hamburg login page script for next-action not found")

            script_response = await library.session.get(
                f"{HAMBURG_BASE_URL}{script_match.group(0)}",
                headers=HAMBURG_PAGE_HEADERS,
                timeout=HAMBURG_LOGIN_TIMEOUT,
            )
            script_response.raise_for_status()

            action_match = NEXT_ACTION_PATTERN.search(script_response.text)
            if not action_match:
                raise ValueError("Hamburg next-action token not found in login script")

            self._next_action = action_match.group(0)
        except Exception as err:  # endpoint may change or be blocked
            LOGGER.debug(
                "Hamburg next-action discovery failed, skipping next-action header: %s",
                err,
            )
            return None

        return self._next_action

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
