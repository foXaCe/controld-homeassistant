"""Config flow for ControlD integration."""
import logging
import voluptuous as vol
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_API_TOKEN, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_API_TOKEN): cv.string,
    vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): cv.positive_int,
})


async def validate_api_token(hass: HomeAssistant, api_token: str) -> Dict[str, Any]:
    """Validate the API token by making a test request."""
    import aiohttp

    # Try different authentication methods and endpoints
    auth_methods = [
        # Method 1: Bearer token with users endpoint (working)
        {
            "headers": {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            },
            "url": "https://api.controld.com/users"
        },
        # Method 2: Bearer token with v1/profiles
        {
            "headers": {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json"
            },
            "url": "https://api.controld.com/v1/profiles"
        },
        # Method 3: X-API-Key header
        {
            "headers": {
                "X-API-Key": api_token,
                "Content-Type": "application/json"
            },
            "url": "https://api.controld.com/users"
        },
        # Method 4: Simple Authorization header
        {
            "headers": {
                "Authorization": api_token,
                "Content-Type": "application/json"
            },
            "url": "https://api.controld.com/users"
        }
    ]

    _LOGGER.debug("Validating ControlD API token")

    for i, method in enumerate(auth_methods, 1):
        _LOGGER.debug("Trying authentication method %d: %s", i, method["url"])
        _LOGGER.debug("Headers: %s", {k: v if "Authorization" not in k and "API-Key" not in k else f"***{api_token[-4:] if len(api_token) > 4 else '***'}" for k, v in method["headers"].items()})

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(method["url"], headers=method["headers"]) as resp:
                    _LOGGER.debug("API response status: %s", resp.status)
                    response_text = await resp.text()
                    _LOGGER.debug("API response body: %s", response_text[:200] + "..." if len(response_text) > 200 else response_text)

                    if resp.status == 200:
                        _LOGGER.info("ControlD API token validation successful with method %d", i)
                        return {"title": "ControlD"}
                    elif resp.status == 401:
                        _LOGGER.debug("Method %d failed with 401 - trying next method", i)
                        continue
                    elif resp.status == 403:
                        # Check if it's an IP restriction or read-only token issue
                        try:
                            response_json = await resp.json()
                            error_message = response_json.get("error", {}).get("message", "")
                            if "IP address is not authorized" in error_message:
                                _LOGGER.error("ControlD API: IP address not authorized for this token. Check token IP restrictions in ControlD dashboard.")
                                raise ValueError("ip_not_authorized")
                            elif "read-only token does not have access" in error_message:
                                _LOGGER.error("ControlD API: Read-only token does not have access to this endpoint. Try with a WRITE token.")
                                raise ValueError("readonly_token_no_access")
                        except ValueError:
                            raise
                        except:
                            pass
                        _LOGGER.debug("Method %d failed with 403 - trying next method", i)
                        continue
                    elif resp.status == 400:
                        _LOGGER.debug("Method %d failed with 400 - trying next method", i)
                        continue
                    else:
                        _LOGGER.debug("Method %d failed with unexpected status %s", i, resp.status)
                        continue
        except aiohttp.ClientError as err:
            _LOGGER.debug("Method %d failed with connection error: %s", i, err)
            continue
        except Exception as err:
            _LOGGER.debug("Method %d failed with unexpected error: %s", i, err)
            continue

    # If all methods failed, raise appropriate error
    _LOGGER.error("ControlD API token validation failed with all methods")
    raise ValueError("invalid_auth")


class ControlDConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ControlD."""

    VERSION = 1

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_api_token(self.hass, user_input[CONF_API_TOKEN])
            except ValueError as err:
                if str(err) == "invalid_auth":
                    errors["base"] = "invalid_auth"
                elif str(err) == "ip_not_authorized":
                    errors["base"] = "ip_not_authorized"
                elif str(err) == "readonly_token_no_access":
                    errors["base"] = "readonly_token_no_access"
                else:
                    errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "api_url": "https://controld.com/account"
            }
        )

    @staticmethod
    @config_entries.HANDLERS.register(DOMAIN)
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return ControlDOptionsFlowHandler(config_entry)


class ControlDOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                    ),
                ): cv.positive_int,
            }),
        )