"""Config flow for Library integration."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import Library
from .const import (
    CONF_COUNTRY,
    CONF_GET_EREOLEN,
    CONF_GET_RESERVATIONS,
    CONF_MUNICIPALITY,
    DOMAIN,
    LIBRARIES_BY_COUNTRY,
    LOGGER,
)


def get_country_options() -> dict[str, str]:
    return {country.title(): country for country in sorted(LIBRARIES_BY_COUNTRY.keys())}


def get_municipality_options(country: str | None = None) -> dict[str, str]:
    if country and country in LIBRARIES_BY_COUNTRY:
        libraries = LIBRARIES_BY_COUNTRY[country]
        return {library.name: municipality for municipality, library in libraries.items()}
    return {
        f"{c.title()} - {library.name}": municipality
        for c, libs in LIBRARIES_BY_COUNTRY.items()
        for municipality, library in libs.items()
    }


class LibraryOptionsFlowHandler(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            for key, value in self.entry.data.items():
                if key not in user_input.keys():
                    user_input[key] = value
            self.hass.config_entries.async_update_entry(
                self.entry, data=user_input, options=self.entry.options
            )
            self.async_abort(reason="configuration updated")
            return self.async_create_entry(title="", data={})

        default_get_ereolen = True
        if self.entry.data.get(CONF_GET_EREOLEN) is not None:
            default_get_ereolen = self.entry.data.get(CONF_GET_EREOLEN)

        default_get_reservations = True
        if self.entry.data.get(CONF_GET_RESERVATIONS) is not None:
            default_get_reservations = self.entry.data.get(CONF_GET_RESERVATIONS)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_GET_RESERVATIONS, default=default_get_reservations
                    ): bool,
                    vol.Required(CONF_GET_EREOLEN, default=default_get_ereolen): bool,
                }
            ),
        )


class LibraryConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Library."""

    VERSION = 1

    def __init__(self):
        self.country = None
        self.municipality = None
        self.user_id = None
        self.pin = None
        self.get_ereolen = None
        self.get_reservations = None
        self.entry = None
        self.user_real_name = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — country selection."""
        if user_input is not None:
            self.country = get_country_options()[user_input[CONF_COUNTRY]]
            return await self.async_step_library()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COUNTRY): vol.In(sorted(get_country_options().keys())),
                }
            ),
        )

    async def async_step_library(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle library and credentials step."""
        errors: dict[str, str] = {}

        municipality_options = get_municipality_options(self.country)

        if user_input is not None:
            try:
                library = Library(
                    municipality=municipality_options[user_input[CONF_MUNICIPALITY]],
                    user_id=user_input[CONF_USERNAME],
                    pin=user_input[CONF_PASSWORD],
                    hass=self.hass,
                )
                await library.authenticate()
                profile_info = await library.get_profile_info()
                self.user_real_name = profile_info.name
            except Exception as ex:  # pylint: disable=broad-except
                LOGGER.debug("Could not log in to Library, %s", ex)
                errors["base"] = "invalid_auth"
            else:
                self.municipality = municipality_options[user_input[CONF_MUNICIPALITY]]
                self.user_id = user_input[CONF_USERNAME]
                self.pin = user_input[CONF_PASSWORD]
                return await self.async_step_options()

        municipalities = sorted(municipality_options.keys())

        return self.async_show_form(
            step_id="library",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MUNICIPALITY): vol.In(municipalities),
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self.get_ereolen = user_input[CONF_GET_EREOLEN]
            self.get_reservations = user_input[CONF_GET_RESERVATIONS]
            return self.async_create_entry(
                title=f"{self.user_real_name} - {self.municipality}",
                data={
                    CONF_MUNICIPALITY: self.municipality,
                    CONF_USERNAME: self.user_id,
                    CONF_PASSWORD: self.pin,
                    CONF_GET_EREOLEN: self.get_ereolen,
                    CONF_GET_RESERVATIONS: self.get_reservations,
                },
            )
        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GET_RESERVATIONS, default=True): bool,
                    vol.Required(CONF_GET_EREOLEN, default=True): bool,
                },
            ),
        )

    async def async_step_reauth(self, _: dict[str, Any]) -> FlowResult:
        """Handle initiation of re-authentication with Library."""
        self.entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication with Library."""
        errors: dict[str, str] = {}

        municipality_options = get_municipality_options()

        if user_input is not None:
            try:
                # Instantiate library client and log in
                library = Library(
                    municipality=municipality_options[user_input[CONF_MUNICIPALITY]],
                    user_id=user_input[CONF_USERNAME],
                    pin=user_input[CONF_PASSWORD],
                    hass=self.hass,
                )
                await library.authenticate()
            except Exception as ex:  # pylint: disable=broad-except
                LOGGER.debug("Could not log in to Library, %s", ex)
                errors["base"] = "invalid_auth"
            else:
                data = self.entry.data.copy()
                self.hass.config_entries.async_update_entry(
                    self.entry,
                    data={
                        **data,
                        CONF_MUNICIPALITY: municipality_options[
                            user_input[CONF_MUNICIPALITY]
                        ],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.entry.entry_id)
                )
            return self.async_abort(reason="reauth_successful")

        municipalities = sorted(municipality_options.keys())

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MUNICIPALITY): vol.In(municipalities),
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return LibraryOptionsFlowHandler(config_entry)
