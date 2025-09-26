"""
ControlD integration for Home Assistant.
"""
import logging
import voluptuous as vol
import aiohttp
import async_timeout
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, API_BASE_URL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ControlD from a config entry."""
    from .sensor import ControlDDataUpdateCoordinator

    _LOGGER.info("Setting up ControlD integration")
    _LOGGER.debug("Entry ID: %s", entry.entry_id)
    _LOGGER.debug("Entry data keys: %s", list(entry.data.keys()))
    _LOGGER.debug("Entry options: %s", entry.options)

    try:
        # Create coordinator
        _LOGGER.debug("Creating ControlD data coordinator")
        coordinator = ControlDDataUpdateCoordinator(hass, entry)

        _LOGGER.debug("Performing initial data refresh")
        await coordinator.async_config_entry_first_refresh()

        _LOGGER.debug("Initial data refresh completed, coordinator data available: %s",
                     bool(coordinator.data))

        # Store the coordinator
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Forward the setup to the platforms
        _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Register services
        await _async_setup_services(hass, coordinator)

        _LOGGER.info("ControlD integration setup completed successfully")
        return True

    except Exception as err:
        _LOGGER.exception("Failed to setup ControlD integration: %s", err)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading ControlD integration")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _async_setup_services(hass: HomeAssistant, coordinator) -> None:
    """Set up ControlD services."""

    async def learn_ip_service(call: ServiceCall) -> None:
        """Learn IP address for device access."""
        device_id = call.data.get("device_id")
        ip_address = call.data.get("ip_address")

        headers = {
            "Authorization": f"Bearer {coordinator.api_token}",
            "Content-Type": "application/json"
        }

        data = {}
        if ip_address:
            data["ip"] = ip_address

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{API_BASE_URL}/access/{device_id}",
                        headers=headers,
                        json=data
                    ) as resp:
                        if resp.status == 200:
                            _LOGGER.info("IP learned successfully for device %s", device_id)
                            await coordinator.async_request_refresh()
                        else:
                            _LOGGER.error("Failed to learn IP for device %s: %s", device_id, resp.status)
        except Exception as err:
            _LOGGER.error("Error learning IP: %s", err)

    async def delete_learned_ip_service(call: ServiceCall) -> None:
        """Delete learned IP address."""
        device_id = call.data.get("device_id")
        ip_address = call.data.get("ip_address")

        headers = {
            "Authorization": f"Bearer {coordinator.api_token}",
            "Content-Type": "application/json"
        }

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.delete(
                        f"{API_BASE_URL}/access/{device_id}/{ip_address}",
                        headers=headers
                    ) as resp:
                        if resp.status == 200:
                            _LOGGER.info("IP %s deleted successfully from device %s", ip_address, device_id)
                            await coordinator.async_request_refresh()
                        else:
                            _LOGGER.error("Failed to delete IP %s from device %s: %s", ip_address, device_id, resp.status)
        except Exception as err:
            _LOGGER.error("Error deleting IP: %s", err)

    async def create_device_service(call: ServiceCall) -> None:
        """Create a new ControlD device."""
        name = call.data.get("name")
        profile_id = call.data.get("profile_id")
        device_type = call.data.get("device_type", "other")

        headers = {
            "Authorization": f"Bearer {coordinator.api_token}",
            "Content-Type": "application/json"
        }

        data = {
            "name": name,
            "profile": profile_id,
            "icon": device_type
        }

        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{API_BASE_URL}/devices",
                        headers=headers,
                        json=data
                    ) as resp:
                        if resp.status == 200:
                            _LOGGER.info("Device %s created successfully", name)
                            await coordinator.async_request_refresh()
                        else:
                            _LOGGER.error("Failed to create device %s: %s", name, resp.status)
        except Exception as err:
            _LOGGER.error("Error creating device: %s", err)

    async def bulk_toggle_filters_service(call: ServiceCall) -> None:
        """Bulk toggle filters by category."""
        profile_id = call.data.get("profile_id")
        filter_category = call.data.get("filter_category")
        enable = call.data.get("enable", True)

        filter_categories = {
            "security": ["malware", "phishing", "typo", "nrd"],
            "privacy": ["ads", "social", "iot"],
            "adult_content": ["porn"],
            "social": ["social"],
            "all": []  # Will be populated with all available filters
        }

        headers = {
            "Authorization": f"Bearer {coordinator.api_token}",
            "Content-Type": "application/json"
        }

        # Get current profile data to find filters
        if coordinator.data and "profiles" in coordinator.data:
            profiles = coordinator.data["profiles"].get("profiles", [])
            target_profile = None
            for profile in profiles:
                if profile.get("PK") == profile_id:
                    target_profile = profile
                    break

            if not target_profile:
                _LOGGER.error("Profile %s not found", profile_id)
                return

            filters_to_toggle = []
            if filter_category == "all":
                filters_to_toggle = [f.get("PK") for f in target_profile.get("filters", [])]
            else:
                category_filters = filter_categories.get(filter_category, [])
                for filter_item in target_profile.get("filters", []):
                    if filter_item.get("PK") in category_filters:
                        filters_to_toggle.append(filter_item.get("PK"))

            # Toggle each filter
            for filter_id in filters_to_toggle:
                try:
                    async with async_timeout.timeout(5):
                        async with aiohttp.ClientSession() as session:
                            async with session.put(
                                f"{API_BASE_URL}/profiles/{profile_id}/filters/{filter_id}",
                                headers=headers,
                                json={"status": 1 if enable else 0}
                            ) as resp:
                                if resp.status == 200:
                                    _LOGGER.info("Filter %s %s in profile %s",
                                                filter_id,
                                                "enabled" if enable else "disabled",
                                                profile_id)
                                else:
                                    _LOGGER.error("Failed to toggle filter %s: %s", filter_id, resp.status)
                except Exception as err:
                    _LOGGER.error("Error toggling filter %s: %s", filter_id, err)

            # Refresh coordinator data
            await coordinator.async_request_refresh()

    # Register services
    hass.services.async_register(
        DOMAIN,
        "learn_ip",
        learn_ip_service,
        schema=vol.Schema({
            vol.Required("device_id"): cv.string,
            vol.Optional("ip_address"): cv.string,
        })
    )

    hass.services.async_register(
        DOMAIN,
        "delete_learned_ip",
        delete_learned_ip_service,
        schema=vol.Schema({
            vol.Required("device_id"): cv.string,
            vol.Required("ip_address"): cv.string,
        })
    )

    hass.services.async_register(
        DOMAIN,
        "create_device",
        create_device_service,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Required("profile_id"): cv.string,
            vol.Optional("device_type", default="other"): cv.string,
        })
    )

    hass.services.async_register(
        DOMAIN,
        "bulk_toggle_filters",
        bulk_toggle_filters_service,
        schema=vol.Schema({
            vol.Required("profile_id"): cv.string,
            vol.Required("filter_category"): vol.In(["security", "privacy", "adult_content", "social", "all"]),
            vol.Optional("enable", default=True): cv.boolean,
        })
    )

    _LOGGER.info("ControlD services registered successfully")