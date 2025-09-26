"""ControlD sensor platform."""
import asyncio
import logging
from datetime import timedelta
import aiohttp
import async_timeout

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, API_BASE_URL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ControlD sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        ControlDProfilesSensor(coordinator),
        ControlDDevicesSensor(coordinator),
        ControlDActiveDevicesSensor(coordinator),
        ControlDTotalClientsSensor(coordinator),
        ControlDTotalIPsSensor(coordinator),
        ControlDRouterDevicesSensor(coordinator),
        ControlDMobileDevicesSensor(coordinator),
    ]

    # Add individual device sensors
    if coordinator.data and "devices" in coordinator.data:
        devices = coordinator.data["devices"].get("devices", [])
        for device in devices:
            entities.append(ControlDDeviceClientsSensor(coordinator, device))
            entities.append(ControlDDeviceIPsSensor(coordinator, device))

    async_add_entities(entities, update_before_add=True)


class ControlDDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching ControlD data from API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.api_token = entry.data["api_token"]
        update_interval_seconds = entry.options.get("update_interval", 30)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
        )

    async def _async_update_data(self):
        """Update data via library."""
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        _LOGGER.debug("Starting ControlD data update")
        _LOGGER.debug("API base URL: %s", API_BASE_URL)
        _LOGGER.debug("Using API token: ***%s", self.api_token[-4:] if len(self.api_token) > 4 else "****")

        try:
            async with async_timeout.timeout(30):
                async with aiohttp.ClientSession() as session:
                    # Get profiles
                    _LOGGER.debug("Fetching profiles from API")
                    async with session.get(f"{API_BASE_URL}/profiles", headers=headers) as resp:
                        _LOGGER.debug("Profiles API response status: %s", resp.status)
                        if resp.status != 200:
                            response_text = await resp.text()
                            _LOGGER.error("Profiles API error %s: %s", resp.status, response_text)
                            raise UpdateFailed(f"Error communicating with profiles API: {resp.status}")
                        profiles_response = await resp.json()
                        profiles_data = profiles_response.get("body", {})
                        _LOGGER.debug("Profiles data received: %s profiles", len(profiles_data.get("profiles", [])))

                    # Get devices
                    _LOGGER.debug("Fetching devices from API")
                    async with session.get(f"{API_BASE_URL}/devices", headers=headers) as resp:
                        _LOGGER.debug("Devices API response status: %s", resp.status)
                        if resp.status != 200:
                            response_text = await resp.text()
                            _LOGGER.error("Devices API error %s: %s", resp.status, response_text)
                            raise UpdateFailed(f"Error communicating with devices API: {resp.status}")
                        devices_response = await resp.json()
                        devices_data = devices_response.get("body", {})
                        _LOGGER.debug("Devices data received: %s devices", len(devices_data.get("devices", [])))

                    # Get detailed profile data with filters and services
                    detailed_profiles = []
                    for profile in profiles_data.get("profiles", []):
                        profile_id = profile.get("PK")
                        if profile_id:
                            # Get filters for this profile
                            try:
                                async with session.get(f"{API_BASE_URL}/profiles/{profile_id}/filters", headers=headers) as resp:
                                    if resp.status == 200:
                                        filters_response = await resp.json()
                                        profile["filters"] = filters_response.get("body", {}).get("filters", [])
                                    else:
                                        profile["filters"] = []
                            except Exception as err:
                                _LOGGER.debug("Could not get filters for profile %s: %s", profile_id, err)
                                profile["filters"] = []

                            # Get services for this profile
                            try:
                                async with session.get(f"{API_BASE_URL}/profiles/{profile_id}/services", headers=headers) as resp:
                                    if resp.status == 200:
                                        services_response = await resp.json()
                                        profile["services"] = services_response.get("body", {}).get("services", [])
                                    else:
                                        profile["services"] = []
                            except Exception as err:
                                _LOGGER.debug("Could not get services for profile %s: %s", profile_id, err)
                                profile["services"] = []

                            # Get options for this profile
                            try:
                                async with session.get(f"{API_BASE_URL}/profiles/{profile_id}/options", headers=headers) as resp:
                                    if resp.status == 200:
                                        options_response = await resp.json()
                                        profile["options"] = options_response.get("body", {}).get("options", [])
                                    else:
                                        profile["options"] = []
                            except Exception as err:
                                _LOGGER.debug("Could not get options for profile %s: %s", profile_id, err)
                                profile["options"] = []

                        detailed_profiles.append(profile)

                    _LOGGER.info("ControlD data update completed successfully")
                    return {
                        "profiles": {"profiles": detailed_profiles},
                        "devices": devices_data,
                    }

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout communicating with ControlD API: %s", err)
            raise UpdateFailed(f"Timeout communicating with API: {err}")
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error communicating with ControlD API: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}")
        except Exception as err:
            _LOGGER.exception("Unexpected error during ControlD data update: %s", err)
            raise UpdateFailed(f"Unexpected error: {err}")


class ControlDSensorBase(CoordinatorEntity, SensorEntity):
    """Base ControlD sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, sensor_type: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"controld_{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "controld_main")},
            "name": "ControlD",
            "manufacturer": "ControlD",
            "model": "DNS Service",
        }


class ControlDProfilesSensor(ControlDSensorBase):
    """ControlD profiles total sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "profiles_total")
        self._attr_name = "ControlD Profiles Total"
        self._attr_icon = "mdi:shield-check"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "profiles" in self.coordinator.data:
            profiles = self.coordinator.data["profiles"]
            return len(profiles.get("profiles", []))
        return 0


class ControlDDevicesSensor(ControlDSensorBase):
    """ControlD devices total sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "devices_total")
        self._attr_name = "ControlD Devices Total"
        self._attr_icon = "mdi:devices"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            return len(devices.get("devices", []))
        return 0


class ControlDActiveDevicesSensor(ControlDSensorBase):
    """ControlD active devices sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "devices_active")
        self._attr_name = "ControlD Active Devices"
        self._attr_icon = "mdi:devices"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            active_count = 0
            for device in devices.get("devices", []):
                if device.get("status") == 1:
                    active_count += 1
            return active_count
        return 0


class ControlDTotalClientsSensor(ControlDSensorBase):
    """ControlD total clients sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "total_clients")
        self._attr_name = "ControlD Total Clients"
        self._attr_icon = "mdi:account-multiple"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            total_clients = 0
            for device in devices.get("devices", []):
                total_clients += device.get("client_count", 0)
            return total_clients
        return 0


class ControlDTotalIPsSensor(ControlDSensorBase):
    """ControlD total IP addresses sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "total_ips")
        self._attr_name = "ControlD Total IP Addresses"
        self._attr_icon = "mdi:ip"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            total_ips = 0
            for device in devices.get("devices", []):
                total_ips += device.get("ip_count", 0)
            return total_ips
        return 0


class ControlDRouterDevicesSensor(ControlDSensorBase):
    """ControlD router devices sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "router_devices")
        self._attr_name = "ControlD Router Devices"
        self._attr_icon = "mdi:router-wireless"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            router_count = 0
            for device in devices.get("devices", []):
                if device.get("icon") == "router":
                    router_count += 1
            return router_count
        return 0


class ControlDMobileDevicesSensor(ControlDSensorBase):
    """ControlD mobile devices sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, "mobile_devices")
        self._attr_name = "ControlD Mobile Devices"
        self._attr_icon = "mdi:cellphone"

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"]
            mobile_count = 0
            for device in devices.get("devices", []):
                if "mobile" in device.get("icon", ""):
                    mobile_count += 1
            return mobile_count
        return 0


class ControlDDeviceClientsSensor(CoordinatorEntity, SensorEntity):
    """ControlD device clients sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, device_data: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_data = device_data
        self._device_id = device_data.get("PK")
        self._device_name = device_data.get("name", "Unknown Device")
        self._attr_unique_id = f"controld_device_clients_{self._device_id}"
        self._attr_name = f"{self._device_name} Clients"
        self._attr_icon = "mdi:account-multiple"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_device_{self._device_id}")},
            "name": f"ControlD {self._device_name}",
            "manufacturer": "ControlD",
            "model": f"Device ({device_data.get('icon', 'unknown')})",
            "via_device": (DOMAIN, "controld_main"),
        }

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"].get("devices", [])
            for device in devices:
                if device.get("PK") == self._device_id:
                    return device.get("client_count", 0)
        return 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"].get("devices", [])
            for device in devices:
                if device.get("PK") == self._device_id:
                    return {
                        "device_id": device.get("PK"),
                        "device_name": device.get("name"),
                        "device_type": device.get("icon"),
                        "status": "Active" if device.get("status") == 1 else "Inactive",
                        "profile": device.get("profile", {}).get("name", "Unknown"),
                        "last_activity": device.get("last_activity"),
                    }
        return {}


class ControlDDeviceIPsSensor(CoordinatorEntity, SensorEntity):
    """ControlD device IP addresses sensor."""

    def __init__(self, coordinator: ControlDDataUpdateCoordinator, device_data: dict) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device_data = device_data
        self._device_id = device_data.get("PK")
        self._device_name = device_data.get("name", "Unknown Device")
        self._attr_unique_id = f"controld_device_ips_{self._device_id}"
        self._attr_name = f"{self._device_name} IP Addresses"
        self._attr_icon = "mdi:ip"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"controld_device_{self._device_id}")},
            "name": f"ControlD {self._device_name}",
            "manufacturer": "ControlD",
            "model": f"Device ({device_data.get('icon', 'unknown')})",
            "via_device": (DOMAIN, "controld_main"),
        }

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"].get("devices", [])
            for device in devices:
                if device.get("PK") == self._device_id:
                    return device.get("ip_count", 0)
        return 0

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        if self.coordinator.data and "devices" in self.coordinator.data:
            devices = self.coordinator.data["devices"].get("devices", [])
            for device in devices:
                if device.get("PK") == self._device_id:
                    resolvers = device.get("resolvers", {})
                    return {
                        "device_id": device.get("PK"),
                        "device_name": device.get("name"),
                        "doh_url": resolvers.get("doh"),
                        "dot_address": resolvers.get("dot"),
                        "ipv4_resolvers": resolvers.get("v4", []),
                        "ipv6_resolvers": resolvers.get("v6", []),
                    }
        return {}