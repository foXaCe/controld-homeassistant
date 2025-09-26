"""ControlD switch platform."""
import asyncio
import logging
import aiohttp
import async_timeout
import time

from homeassistant.components.switch import SwitchEntity
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
    """Set up ControlD switches based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    # Create switches for each profile
    if coordinator.data and "profiles" in coordinator.data:
        profiles = coordinator.data["profiles"].get("profiles", [])
        for profile in profiles:
            entities.append(ControlDProfileSwitch(coordinator, profile))

            # Add filter switches for each profile
            for filter_data in profile.get("filters", []):
                entities.append(ControlDFilterSwitch(coordinator, profile, filter_data))

            # Add service switches for each profile
            for service_data in profile.get("services", []):
                entities.append(ControlDServiceSwitch(coordinator, profile, service_data))

            # Add option switches/controls for each profile
            for option_data in profile.get("options", []):
                option_switch = ControlDOptionSwitch(coordinator, profile, option_data)
                if option_switch._is_boolean:
                    entities.append(option_switch)

    async_add_entities(entities, update_before_add=True)


class ControlDProfileSwitch(CoordinatorEntity, SwitchEntity):
    """ControlD profile switch."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, profile_data: dict) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._profile_data = profile_data
        self._profile_id = profile_data.get("PK")
        self._attr_unique_id = f"controld_profile_{self._profile_id}"
        self._attr_name = f"ControlD {profile_data.get('name', 'Profile')}"
        self._attr_icon = "mdi:shield-check"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_profile_{self._profile_id}")},
            "name": f"ControlD Profile {profile_data.get('name', 'Unknown')}",
            "manufacturer": "ControlD",
            "model": "DNS Profile",
            "via_device": (DOMAIN, "controld_main"),
        }

    @property
    def is_on(self) -> bool:
        """Return true if the profile is active."""
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    return True  # Profiles are assumed active if they exist
        return False

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    return {
                        "profile_id": profile.get("PK"),
                        "profile_name": profile.get("name"),
                        "updated": profile.get("updated"),
                    }
        return {}

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the profile on."""
        await self._async_toggle_profile(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the profile off."""
        await self._async_toggle_profile(False)

    async def _async_toggle_profile(self, enable: bool) -> None:
        """Toggle profile status."""
        headers = {
            "Authorization": f"Bearer {self.coordinator.api_token}",
            "Content-Type": "application/json"
        }

        data = {
            "status": "active" if enable else "inactive"
        }

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.patch(
                        f"{API_BASE_URL}/profiles/{self._profile_id}",
                        headers=headers,
                        json=data
                    ) as resp:
                        if resp.status == 200:
                            _LOGGER.info(
                                "Profile %s %s successfully",
                                self._profile_id,
                                "enabled" if enable else "disabled"
                            )
                            # Refresh coordinator data
                            await self.coordinator.async_request_refresh()
                        else:
                            _LOGGER.error(
                                "Failed to toggle profile %s: %s",
                                self._profile_id,
                                resp.status
                            )

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while toggling profile %s", self._profile_id)
        except aiohttp.ClientError as err:
            _LOGGER.error("Error toggling profile %s: %s", self._profile_id, err)


class ControlDFilterSwitch(CoordinatorEntity, SwitchEntity):
    """ControlD filter switch."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, profile_data: dict, filter_data: dict) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._profile_data = profile_data
        self._filter_data = filter_data
        self._profile_id = profile_data.get("PK")
        self._filter_id = filter_data.get("PK")
        self._profile_name = profile_data.get("name", "Unknown Profile")
        self._filter_name = filter_data.get("name", "Unknown Filter")

        # Local state management for better UX
        self._local_state = None  # None, True, False
        self._local_state_expires = None
        self._is_updating = False

        self._attr_unique_id = f"controld_filter_{self._profile_id}_{self._filter_id}"
        self._attr_name = f"{self._profile_name} - {self._filter_name}"
        self._update_icon()

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_profile_{self._profile_id}")},
            "name": f"ControlD Profile {self._profile_name}",
            "manufacturer": "ControlD",
            "model": "DNS Profile",
            "via_device": (DOMAIN, "controld_main"),
        }

    def _update_icon(self):
        """Update icon based on current state."""
        if self._is_updating:
            self._attr_icon = "mdi:loading"
        elif self.is_on:
            self._attr_icon = "mdi:filter"
        else:
            self._attr_icon = "mdi:filter-off"

    @property
    def is_on(self) -> bool:
        """Return true if the filter is enabled."""
        current_time = time.time()

        # Debug logging
        _LOGGER.debug(
            "Filter %s is_on check: local_state=%s, expires=%s, current_time=%s, time_left=%s",
            self._filter_id,
            self._local_state,
            self._local_state_expires,
            current_time,
            (self._local_state_expires - current_time) if self._local_state_expires else None
        )

        # Check if we have a local state override that hasn't expired
        if (self._local_state is not None and
            self._local_state_expires is not None and
            current_time < self._local_state_expires):
            _LOGGER.debug("Filter %s using local state: %s", self._filter_id, self._local_state)
            return self._local_state

        # Otherwise, return the actual state from the coordinator
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    for filter_item in profile.get("filters", []):
                        if filter_item.get("PK") == self._filter_id:
                            api_state = filter_item.get("status") == 1
                            _LOGGER.debug("Filter %s using API state: %s", self._filter_id, api_state)
                            return api_state

        _LOGGER.debug("Filter %s defaulting to False", self._filter_id)
        return False

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "profile_id": self._profile_id,
            "profile_name": self._profile_name,
            "filter_id": self._filter_id,
            "filter_name": self._filter_name,
            "description": self._filter_data.get("description", ""),
            "category": self._filter_data.get("category", ""),
        }

    def _get_actual_state_from_coordinator(self) -> bool:
        """Get the actual state from coordinator data without local override."""
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    for filter_item in profile.get("filters", []):
                        if filter_item.get("PK") == self._filter_id:
                            return filter_item.get("status") == 1
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the filter on."""
        _LOGGER.info("Filter %s turn_on called", self._filter_id)
        await self._async_toggle_filter(1)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the filter off."""
        _LOGGER.info("Filter %s turn_off called", self._filter_id)
        await self._async_toggle_filter(0)

    async def _async_toggle_filter(self, status: int) -> None:
        """Toggle filter status."""
        _LOGGER.info("Filter %s toggle to status %s started", self._filter_id, status)

        # Set local state immediately for responsive UI
        self._local_state = bool(status)
        self._local_state_expires = time.time() + 30  # 30 seconds override for ControlD propagation
        self._is_updating = True
        self._update_icon()

        _LOGGER.info(
            "Filter %s local state set: state=%s, expires=%s",
            self._filter_id, self._local_state, self._local_state_expires
        )

        self.async_write_ha_state()

        headers = {
            "Authorization": f"Bearer {self.coordinator.api_token}",
            "Content-Type": "application/json"
        }

        data = {"action": {"do": 0, "status": status}}

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"{API_BASE_URL}/profiles/{self._profile_id}/native/filters/{self._filter_id}",
                        headers=headers,
                        json=data
                    ) as resp:
                        response_text = await resp.text()
                        _LOGGER.info(
                            "Filter API response for %s: status=%s, body=%s",
                            self._filter_id, resp.status, response_text
                        )

                        if resp.status == 200:
                            _LOGGER.info(
                                "Filter %s %s successfully in profile %s",
                                self._filter_id,
                                "enabled" if status else "disabled",
                                self._profile_id
                            )
                            # Wait for ControlD to propagate changes
                            await asyncio.sleep(5)
                            await self.coordinator.async_request_refresh()

                            # Let local state expire naturally instead of clearing immediately
                            _LOGGER.info("Filter %s API success, letting local state expire naturally", self._filter_id)
                        else:
                            _LOGGER.error(
                                "Failed to toggle filter %s in profile %s: %s - %s",
                                self._filter_id,
                                self._profile_id,
                                resp.status,
                                response_text
                            )
                            # Reset local state on error
                            self._local_state = None
                            self._local_state_expires = None

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while toggling filter %s", self._filter_id)
            # Reset local state on timeout
            self._local_state = None
            self._local_state_expires = None
        except aiohttp.ClientError as err:
            _LOGGER.error("Error toggling filter %s: %s", self._filter_id, err)
            # Reset local state on error
            self._local_state = None
            self._local_state_expires = None
        finally:
            # Clear updating state and update icon
            self._is_updating = False
            self._update_icon()
            self.async_write_ha_state()


class ControlDServiceSwitch(CoordinatorEntity, SwitchEntity):
    """ControlD service switch."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, profile_data: dict, service_data: dict) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._profile_data = profile_data
        self._service_data = service_data
        self._profile_id = profile_data.get("PK")
        self._service_id = service_data.get("PK")
        self._profile_name = profile_data.get("name", "Unknown Profile")
        self._service_name = service_data.get("name", "Unknown Service")

        # Local state management for better UX
        self._local_state = None  # None, True, False
        self._local_state_expires = None
        self._is_updating = False

        self._attr_unique_id = f"controld_service_{self._profile_id}_{self._service_id}"
        self._attr_name = f"{self._profile_name} - {self._service_name} Service"
        self._update_icon()

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_profile_{self._profile_id}")},
            "name": f"ControlD Profile {self._profile_name}",
            "manufacturer": "ControlD",
            "model": "DNS Profile",
            "via_device": (DOMAIN, "controld_main"),
        }

    def _update_icon(self):
        """Update icon based on current state."""
        if self._is_updating:
            self._attr_icon = "mdi:loading"
        elif self.is_on:
            self._attr_icon = "mdi:web"
        else:
            self._attr_icon = "mdi:web-off"

    @property
    def is_on(self) -> bool:
        """Return true if the service is enabled."""
        # Check if we have a local state override that hasn't expired
        if (self._local_state is not None and
            self._local_state_expires is not None and
            time.time() < self._local_state_expires):
            return self._local_state

        # Otherwise, return the actual state from the coordinator
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    for service in profile.get("services", []):
                        if service.get("PK") == self._service_id:
                            return service.get("action", {}).get("status") == 1
        return False

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        action_data = self._service_data.get("action", {})
        return {
            "profile_id": self._profile_id,
            "profile_name": self._profile_name,
            "service_id": self._service_id,
            "service_name": self._service_name,
            "category": self._service_data.get("category", ""),
            "action_type": action_data.get("do", 0),
            "unlock_location": self._service_data.get("unlock_location", ""),
            "warning": self._service_data.get("warning", ""),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the service on."""
        await self._async_toggle_service(1)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the service off."""
        await self._async_toggle_service(0)

    async def _async_toggle_service(self, status: int) -> None:
        """Toggle service status."""
        # Set local state immediately for responsive UI
        self._local_state = bool(status)
        self._local_state_expires = time.time() + 30  # 30 seconds override for ControlD propagation
        self._is_updating = True
        self._update_icon()
        self.async_write_ha_state()

        headers = {
            "Authorization": f"Bearer {self.coordinator.api_token}",
            "Content-Type": "application/json"
        }

        # Keep the existing action type but change status
        current_action = self._service_data.get("action", {})
        data = {
            "do": current_action.get("do", 1),
            "status": status
        }

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.put(
                        f"{API_BASE_URL}/profiles/{self._profile_id}/services/{self._service_id}",
                        headers=headers,
                        json=data
                    ) as resp:
                        response_text = await resp.text()
                        _LOGGER.info(
                            "Service API response for %s: status=%s, body=%s",
                            self._service_id, resp.status, response_text
                        )

                        if resp.status == 200:
                            _LOGGER.info(
                                "Service %s %s successfully in profile %s",
                                self._service_id,
                                "enabled" if status else "disabled",
                                self._profile_id
                            )
                            # Wait for ControlD to propagate changes
                            await asyncio.sleep(5)
                            await self.coordinator.async_request_refresh()

                            # Clear local state after propagation
                            self._local_state = None
                            self._local_state_expires = None
                        else:
                            _LOGGER.error(
                                "Failed to toggle service %s in profile %s: %s - %s",
                                self._service_id,
                                self._profile_id,
                                resp.status,
                                response_text
                            )
                            # Reset local state on error
                            self._local_state = None
                            self._local_state_expires = None

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while toggling service %s", self._service_id)
            # Reset local state on timeout
            self._local_state = None
            self._local_state_expires = None
        except aiohttp.ClientError as err:
            _LOGGER.error("Error toggling service %s: %s", self._service_id, err)
            # Reset local state on error
            self._local_state = None
            self._local_state_expires = None
        finally:
            # Clear updating state and update icon
            self._is_updating = False
            self._update_icon()
            self.async_write_ha_state()


class ControlDOptionSwitch(CoordinatorEntity, SwitchEntity):
    """ControlD option switch for boolean options."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, profile_data: dict, option_data: dict) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._profile_data = profile_data
        self._option_data = option_data
        self._profile_id = profile_data.get("PK")
        self._option_id = option_data.get("PK")
        self._profile_name = profile_data.get("name", "Unknown Profile")
        self._option_name = self._get_option_display_name(self._option_id)

        # Only create switches for boolean-like options
        self._is_boolean = self._is_boolean_option()
        if not self._is_boolean:
            return

        # Local state management for better UX
        self._local_state = None  # None, True, False
        self._local_state_expires = None
        self._is_updating = False

        self._attr_unique_id = f"controld_option_{self._profile_id}_{self._option_id}"
        self._attr_name = f"{self._profile_name} - {self._option_name}"
        self._update_icon()

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_profile_{self._profile_id}")},
            "name": f"ControlD Profile {self._profile_name}",
            "manufacturer": "ControlD",
            "model": "DNS Profile",
            "via_device": (DOMAIN, "controld_main"),
        }

    def _update_icon(self):
        """Update icon based on current state."""
        if self._is_updating:
            self._attr_icon = "mdi:loading"
        elif self.is_on:
            self._attr_icon = "mdi:cog"
        else:
            self._attr_icon = "mdi:cog-off"

    def _is_boolean_option(self) -> bool:
        """Check if this option should be represented as a boolean switch."""
        boolean_options = ["block_rfc1918", "log_queries"]
        return self._option_id in boolean_options

    def _get_option_display_name(self, option_id: str) -> str:
        """Get human-readable name for option."""
        names = {
            "block_rfc1918": "Block Private IPs",
            "ai_malware": "AI Malware Detection",
            "log_queries": "Log Queries",
        }
        return names.get(option_id, option_id.replace("_", " ").title())

    @property
    def is_on(self) -> bool:
        """Return true if the option is enabled."""
        if not self._is_boolean:
            return False

        # Check if we have a local state override that hasn't expired
        if (self._local_state is not None and
            self._local_state_expires is not None and
            time.time() < self._local_state_expires):
            return self._local_state

        # Otherwise, return the actual state from the coordinator
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"].get("profiles", [])
            for profile in profiles:
                if profile.get("PK") == self._profile_id:
                    for option in profile.get("options", []):
                        if option.get("PK") == self._option_id:
                            return bool(option.get("value", 0))
        return False

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        return {
            "profile_id": self._profile_id,
            "profile_name": self._profile_name,
            "option_id": self._option_id,
            "option_name": self._option_name,
            "value": self._option_data.get("value", 0),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the option on."""
        await self._async_toggle_option(1)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the option off."""
        await self._async_toggle_option(0)

    async def _async_toggle_option(self, value: int) -> None:
        """Toggle option value."""
        # Set local state immediately for responsive UI
        self._local_state = bool(value)
        self._local_state_expires = time.time() + 30  # 30 seconds override for ControlD propagation
        self._is_updating = True
        self._update_icon()
        self.async_write_ha_state()

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
                            "Option API response for %s: status=%s, body=%s",
                            self._option_id, resp.status, response_text
                        )

                        if resp.status == 200:
                            _LOGGER.info(
                                "Option %s %s successfully in profile %s",
                                self._option_id,
                                "enabled" if value else "disabled",
                                self._profile_id
                            )
                            # Wait for ControlD to propagate changes
                            await asyncio.sleep(5)
                            await self.coordinator.async_request_refresh()

                            # Clear local state after propagation
                            self._local_state = None
                            self._local_state_expires = None
                        else:
                            _LOGGER.error(
                                "Failed to toggle option %s in profile %s: %s - %s",
                                self._option_id,
                                self._profile_id,
                                resp.status,
                                response_text
                            )
                            # Reset local state on error
                            self._local_state = None
                            self._local_state_expires = None

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while toggling option %s", self._option_id)
            # Reset local state on timeout
            self._local_state = None
            self._local_state_expires = None
        except aiohttp.ClientError as err:
            _LOGGER.error("Error toggling option %s: %s", self._option_id, err)
            # Reset local state on error
            self._local_state = None
            self._local_state_expires = None
        finally:
            # Clear updating state and update icon
            self._is_updating = False
            self._update_icon()
            self.async_write_ha_state()