"""Config flow for itron integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_MUNICIPALITY, DOMAIN, CONF_COST_OPTION
from .exceptions import CannotConnect, InvalidAuth
from .itron import Itron, get_supported_municipality_names

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MUNICIPALITY): vol.In(get_supported_municipality_names()),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    api = Itron(
        async_create_clientsession(hass),
        data[CONF_MUNICIPALITY],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )

    await api.async_login()
    return {
        "title": f"{data[CONF_MUNICIPALITY]} ({data[CONF_USERNAME]})",
    }


class ItronOptionsFlowHandler(OptionsFlow):
    """Handle itron options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize itron options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage itron options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COST_OPTION,
                        default=self.config_entry.options.get(CONF_COST_OPTION, 1.0),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=True)),
                }
            ),
        )


class ItronConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for itron."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ItronOptionsFlowHandler:
        """Get the options flow for this handler."""
        return ItronOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
