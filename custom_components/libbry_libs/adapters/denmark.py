import asyncio
import re

try:
    # pylint: disable=invalid-name
    from homeassistant.helpers.httpx_client import create_async_httpx_client, httpx
except ImportError:
    import httpx

    create_async_httpx_client = httpx.AsyncClient

from ..const import LOGGER
from ..models import EreolenLoan, EreolenReservation, Loan, ProfileInfo, Reservation
from .base import AdapterRegistry, LibraryAdapter

COMMON_LOGIN_BASE_URL = "https://login.bib.dk"
COMMON_LOGIN_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,da;q=0.8",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://login.bib.dk",
    "Referer": "https://login.bib.dk/login",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "sec-ch-ua": '"Chromium";v="130", "Microsoft Edge";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
FBS_OPEN_PLATFORM_BASE_URL = "https://fbs-openplatform.dbc.dk"
INFO_BASE_URL = "https://temp.fbi-api.dbc.dk"
INFO_GRAPH_QL_QUERY = "query getManifestationViaMaterialByFaust($faust: String!) { manifestation(faust: $faust) { titles { full } creators { display } abstract pid } }"
IMAGE_FROM_PID_GRAPH_QL_QUERY = "query GetCoversByPids($pids: [String!]!) {manifestations(pid: $pids) {pid, cover {small {url} medium {url} large {url}}}}"
SEARCH_ISBN_GRAPH_QL_QUERY = "query GetBestRepresentationPidByIsbn($cql: String!, $offset: Int!, $limit: PaginationLimitScalar!, $filters: ComplexSearchFiltersInput!) {complexSearch(cql: $cql, filters: $filters) {works(offset: $offset, limit: $limit) {workId manifestations {bestRepresentation {pid}}}}}"
PUBHUB_BASE_URL = "https://pubhub-openplatform.dbc.dk"
DEFAULT_IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/6/65/No-Image-Placeholder.svg/128px-No-Image-Placeholder.svg.png"


def reauth_on_fail(func):
    async def wrapper(self, library, *args):
        try:
            LOGGER.debug(func.__name__)
            if not library.user_token:
                await self.authenticate(library)
            return await func(self, library, *args)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                await self.authenticate(library)
                return await func(self, library, *args)
            if e.response.status_code >= 500:
                LOGGER.debug(e, exc_info=True)
                LOGGER.debug("Unknown error, retrying in 30sec")
                await asyncio.sleep(30)
                return await func(self, library, *args)
            raise e
        except httpx.ConnectError as e:
            LOGGER.debug(e)
            LOGGER.debug("Connect error, retrying in 30sec", exc_info=True)
            await asyncio.sleep(30)
            return await func(self, library, *args)
        except Exception as e:
            LOGGER.debug(e)
            LOGGER.debug("Unknown error, retrying in 30sec", exc_info=True)
            await asyncio.sleep(30)
            return await func(self, library, *args)

    return wrapper


@AdapterRegistry.register
class DenmarkLibraryAdapter(LibraryAdapter):
    @property
    def name(self) -> str:
        return "denmark"

    async def authenticate(self, library) -> None:
        try:
            LOGGER.debug("Authenticating")
            library.session = (
                create_async_httpx_client()
                if not library.hass
                else create_async_httpx_client(library.hass)
            )
            library.session.cookies.clear()
            response = await library.session.get(
                library.municipality.url, follow_redirects=True, timeout=None
            )
            response.raise_for_status()
            login_page_request = await library.session.get(
                f"{library.municipality.url}/login?current-path=/user/me/dashboard",
                follow_redirects=True,
                timeout=None,
            )
            login_page_request.raise_for_status()
            login_page_text = login_page_request.text
            login_path = re.search(r'action="(.*?)"', login_page_text).group(1)
            common_login_url = f"{COMMON_LOGIN_BASE_URL}{login_path}"
            payload = {
                "agency": library.municipality.branch_id,
                "libraryName": library.municipality.name,
                "loginBibDkUserId": library.user_id,
                "pincode": library.pin,
            }
            response = await library.session.post(
                common_login_url,
                headers=COMMON_LOGIN_HEADERS,
                data=payload,
                follow_redirects=True,
                timeout=None,
            )
            response.raise_for_status()
            token_response = await library.session.get(
                f"{library.municipality.url}/dpl-react/user-tokens",
                follow_redirects=False,
                timeout=None,
            )
            token_response.raise_for_status()
            token_text = token_response.text

            library.user_token = re.search(r'"user",\s*"(.*?)"', token_text).group(1)
            library.library_token = re.search(
                r'"library",\s*"(.*?)"', token_text
            ).group(1)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                LOGGER.debug(e, exc_info=True)
                LOGGER.debug("Unknown error, retrying in 30sec")
                await asyncio.sleep(30)
                return await self.authenticate(library)
            raise e
        except httpx.ConnectError as e:
            LOGGER.debug(e)
            LOGGER.debug("Connect error, retrying in 30sec", exc_info=True)
            await asyncio.sleep(30)
            return await self.authenticate(library)
        except Exception as e:
            LOGGER.debug(e)
            LOGGER.debug("Unknown error, retrying in 30sec", exc_info=True)
            await asyncio.sleep(30)
            return await self.authenticate(library)

    @reauth_on_fail
    async def get_profile_info(self, library) -> ProfileInfo:
        headers = {"Authorization": library.user_bearer_token}
        profile_response = await library.session.get(
            f"{FBS_OPEN_PLATFORM_BASE_URL}/external/agencyid/patrons/patronid/v4",
            headers=headers,
            follow_redirects=True,
            timeout=None,
        )
        profile_response.raise_for_status()
        return ProfileInfo(profile_response.json()["patron"])

    @reauth_on_fail
    async def get_fees(self, library):
        headers = {"Authorization": library.user_bearer_token}
        params = {"includepaid": True, "includenonpayable": True}
        fee_response = await library.session.get(
            f"{FBS_OPEN_PLATFORM_BASE_URL}/external/agencyid/patron/patronid/fees/v2",
            headers=headers,
            follow_redirects=True,
            params=params,
            timeout=None,
        )
        fee_response.raise_for_status()
        return fee_response.json()

    @reauth_on_fail
    async def get_loans(self, library):
        headers = {"Authorization": library.user_bearer_token}
        loans_response = await library.session.get(
            f"{FBS_OPEN_PLATFORM_BASE_URL}/external/agencyid/patrons/patronid/loans/v2",
            headers=headers,
            follow_redirects=True,
            timeout=None,
        )
        loans_response.raise_for_status()
        tasks = []
        for res in loans_response.json():
            tasks.append(
                asyncio.get_event_loop().create_task(
                    self.get_info(library, res["loanDetails"]["recordId"], res, Loan)
                )
            )
        return await library.unpack_results(tasks)

    @reauth_on_fail
    async def get_ereolen_loans(self, library):
        headers = {"Authorization": library.user_bearer_token}
        loans_response = await library.session.get(
            f"{PUBHUB_BASE_URL}/v1/user/loans",
            headers=headers,
            follow_redirects=True,
            timeout=None,
        )
        loans_response.raise_for_status()
        tasks = []
        for res in loans_response.json()["loans"]:
            tasks.append(
                asyncio.get_event_loop().create_task(
                    self.get_ereolen_info(
                        library,
                        res["libraryBook"]["identifier"],
                        res,
                        EreolenLoan,
                    )
                )
            )
        return await library.unpack_results(tasks)

    @reauth_on_fail
    async def get_reservations(self, library) -> list[Reservation]:
        headers = {"Authorization": library.user_bearer_token}
        reservations_response = await library.session.get(
            f"{FBS_OPEN_PLATFORM_BASE_URL}/external/v1/agencyid/patrons/patronid/reservations/v2",
            headers=headers,
            follow_redirects=True,
            timeout=None,
        )
        reservations_response.raise_for_status()
        tasks = []
        for res in reservations_response.json():
            tasks.append(
                asyncio.get_event_loop().create_task(
                    self.get_info(library, res["recordId"], res, Reservation)
                )
            )
        return await library.unpack_results(tasks)

    @reauth_on_fail
    async def get_ereolen_reservations(self, library):
        headers = {"Authorization": library.user_bearer_token}
        reservations_response = await library.session.get(
            f"{PUBHUB_BASE_URL}/v1/user/reservations",
            headers=headers,
            follow_redirects=True,
            timeout=None,
        )
        reservations_response.raise_for_status()
        tasks = []
        for res in reservations_response.json()["reservations"]:
            tasks.append(
                asyncio.get_event_loop().create_task(
                    self.get_ereolen_info(
                        library, res["identifier"], res, EreolenReservation
                    )
                )
            )
        return await library.unpack_results(tasks)

    @reauth_on_fail
    async def get_info(
        self, library, identifier: str, original_object, output_type: type
    ):
        headers = {"Authorization": library.user_bearer_token}
        body = {
            "query": INFO_GRAPH_QL_QUERY,
            "variables": {"faust": identifier},
        }
        tasks = []
        urls = [
            f"{INFO_BASE_URL}/fbcms-vis/graphql",
            f"{INFO_BASE_URL}/DDFCMS-VIS/graphql",
            f"{INFO_BASE_URL}/opac/graphql",
        ]
        for url in urls:
            tasks.append(
                asyncio.get_event_loop().create_task(
                    library.session.post(
                        url, headers=headers, json=body, follow_redirects=False
                    )
                )
            )
        pid = None
        info = None
        results: list[httpx.Response] = await library.unpack_results(tasks)
        for res in results:
            if res.status_code != 200:
                continue
            info = library.get_nested_value(res.json(), ["data", "manifestation"])
            if info is None:
                continue
            pid = info.get("pid")
            if pid is not None:
                break

        if pid is None:
            LOGGER.error(
                "Could not extract PID from object, maybe this municipality uses a new url. MUNICIPALITY=%s",
                library.municipality,
            )

        image_url = await self.get_image_cover(library, pid)
        return output_type(
            original_object,
            info,
            image_url,
        )

    @reauth_on_fail
    async def get_ereolen_info(
        self, library, identifier: str, original_object, output_type: type
    ):
        headers = {"Authorization": library.user_bearer_token}
        info_response = await library.session.get(
            f"{PUBHUB_BASE_URL}/v1/products/{identifier}",
            headers=headers,
            follow_redirects=True,
            timeout=None,
        )
        info_response.raise_for_status()
        info = info_response.json()
        pid = await self.convert_isbn_to_pid(library, identifier)
        image_url = await self.get_image_cover(library, pid)
        return output_type(
            original_object,
            info["product"],
            image_url,
        )

    @reauth_on_fail
    async def convert_isbn_to_pid(self, library, isbn: str):
        try:
            payload = {
                "query": SEARCH_ISBN_GRAPH_QL_QUERY,
                "variables": {
                    "cql": f"term.isbn={isbn}",
                    "offset": 0,
                    "limit": 1,
                    "filters": {},
                },
            }
            headers = {"Authorization": library.library_bearer_token}
            response = await library.session.post(
                f"{INFO_BASE_URL}/fbcms-soeg/graphql",
                headers=headers,
                json=payload,
                follow_redirects=True,
                timeout=None,
            )
            response.raise_for_status()
            return response.json()["data"]["complexSearch"]["works"][0][
                "manifestations"
            ]["bestRepresentation"]["pid"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise e
        except Exception as e:
            LOGGER.exception(e)

    @reauth_on_fail
    async def get_image_cover(self, library, pid: str):
        try:
            payload = {
                "query": IMAGE_FROM_PID_GRAPH_QL_QUERY,
                "variables": {"pids": [pid]},
            }
            image_headers = {"Authorization": library.library_bearer_token}
            image_response = await library.session.post(
                f"{INFO_BASE_URL}/fbcms-soeg/graphql",
                headers=image_headers,
                json=payload,
                follow_redirects=True,
                timeout=None,
            )
            image_response.raise_for_status()
            image_url = None
            image_urls = image_response.json()["data"]["manifestations"][0]["cover"]
            if "small" in image_urls.keys() and "url" in image_urls["small"].keys():
                image_url = image_urls["small"]["url"]
            if "medium" in image_urls.keys() and "url" in image_urls["medium"].keys():
                image_url = image_urls["medium"]["url"]
            if "large" in image_urls.keys() and "url" in image_urls["large"].keys():
                image_url = image_urls["large"]["url"]
            if not image_url:
                LOGGER.debug("No images returned for title")
                LOGGER.debug(image_response.request.__dict__)
            return DEFAULT_IMAGE_URL if not image_url else image_url
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise e
        except Exception as e:
            LOGGER.exception(e)
