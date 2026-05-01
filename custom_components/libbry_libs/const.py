# pylint: disable=line-too-long
import json
import logging
import pathlib
from datetime import timedelta

from .models import LibraryConfig

CONF_COUNTRY = "country"
CONF_GET_EREOLEN = "get_ereolen"
CONF_GET_RESERVATIONS = "get_reservations"
CONF_MUNICIPALITY = "municipality"
COVER_BASE_URL = "https://cover.dandigbib.org"
DEFAULT_SCAN_INTERVAL = timedelta(hours=4)
DOMAIN = "libbry_libs"

LIBRARIES_BY_COUNTRY: dict[str, dict[str, LibraryConfig]] = {}
LIBRARIES: dict[str, LibraryConfig] = {}
with open(
    pathlib.Path(__file__).parent.joinpath("libraries.json"), "r", encoding="UTF8"
) as f:
    LIBRARIES_BY_COUNTRY = LibraryConfig.from_json_by_country(json.loads(f.read()))
    LIBRARIES = {
        key: value
        for country_libraries in LIBRARIES_BY_COUNTRY.values()
        for key, value in country_libraries.items()
    }

LOGGER = logging.getLogger(__package__)
