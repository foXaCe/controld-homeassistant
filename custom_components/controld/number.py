"""ControlD number platform."""
import asyncio
import logging
import aiohttp
import async_timeout

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, API_BASE_URL
from .sensor import ControlDDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ControlD number entities based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Create number entities for numeric options in each profile
    if coordinator.data and "profiles" in coordinator.data:
        profiles = coordinator.data["profiles"].get("profiles", [])
        for profile in profiles:
            for option_data in profile.get("options", []):
                if _is_numeric_option(option_data.get("PK")):
                    entities.append(ControlDOptionNumber(coordinator, profile, option_data))

    async_add_entities(entities, update_before_add=True)


def _is_numeric_option(option_id: str) -> bool:
    """Check if this option should be represented as a number input."""
    numeric_options = ["ai_malware"]
    return option_id in numeric_options


class ControlDOptionNumber(CoordinatorEntity, NumberEntity):
    """ControlD option number input."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, profile_data: dict, option_data: dict) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._profile_data = profile_data
        self._option_data = option_data
        self._profile_id = profile_data.get("PK")
        self._option_id = option_data.get("PK")
        self._profile_name = profile_data.get("name", "Unknown Profile")
        self._option_name = self._get_option_display_name(self._option_id)

        self._attr_unique_id = f"controld_option_number_{self._profile_id}_{self._option_id}"
        self._attr_name = f"{self._profile_name} - {self._option_name}"
        self._attr_icon = "mdi:tune"

        # Set number properties based on option type
        if self._option_id == "ai_malware":
            self._attr_native_min_value = 0.0
            self._attr_native_max_value = 1.0
            self._attr_native_step = 0.1
            self._attr_native_unit_of_measurement = None
        else:
            self._attr_native_min_value = 0
            self._attr_native_max_value = 100
            self._attr_native_step = 1

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_profile_{self._profile_id}")},
            "name": f"ControlD Profile {self._profile_name}",
            "manufacturer": "ControlD",
            "model": "DNS Profile",
            "via_device": (DOMAIN, "controld_main"),
        }

    def _get_option_display_name(self, option_id: str) -> str:
        """Get human-readable name for option."""
        names = {
            "ai_malware": "AI Malware Threshold",
        }
        return names.get(option_id, option_id.replace("_", " ").title())

    @property
    def native_value(self) -> float:
        """Return the current value."""
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    for option in profile.get("options", []):
                        if option.get("PK") == self._option_id:
                            return float(option.get("value", 0))
        return 0.0

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "profile_id": self._profile_id,
            "profile_name": self._profile_name,
            "option_id": self._option_id,
            "option_name": self._option_name,
            "description": "AI-powered malware detection threshold (0.0 = disabled, 1.0 = most strict)",
        }

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        headers = {
            "Authorization": f"Bearer {self.coordinator.api_token}",
            "Content-Type": "application/json"
        }

        data = {"value": value, "status": 1}

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"{API_BASE_URL}/profiles/{self._profile_id}/options/{self._option_id}",
                        headers=headers,
                        json=data
                    ) as resp:
                        response_text = await resp.text()
                        _LOGGER.info(
                            "Number API response for %s: status=%s, body=%s",
                            self._option_id, resp.status, response_text
                        )

                        if resp.status == 200:
                            _LOGGER.info(
                                "Option %s updated to %s in profile %s",
                                self._option_id,
                                value,
                                self._profile_id
                            )
                            await asyncio.sleep(2)
                            await self.coordinator.async_request_refresh()
                        else:
                            _LOGGER.error(
                                "Failed to update option %s in profile %s: %s - %s",
                                self._option_id,
                                self._profile_id,
                                resp.status,
                                response_text
                            )

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while updating option %s", self._option_id)
        except aiohttp.ClientError as err:
            _LOGGER.error("Error updating option %s: %s", self._option_id, err)