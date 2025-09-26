"""Constants for the ControlD integration."""

DOMAIN = "controld"

# API Configuration
API_BASE_URL = "https://api.controld.com"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes

# Configuration
CONF_API_TOKEN = "api_token"
CONF_UPDATE_INTERVAL = "update_interval"

# Attributes
ATTR_PROFILE_ID = "profile_id"
ATTR_PROFILE_NAME = "profile_name"
ATTR_DEVICE_ID = "device_id"
ATTR_DEVICE_NAME = "device_name"
ATTR_LAST_UPDATED = "last_updated"

# Service names
SERVICE_UPDATE_PROFILE = "update_profile"
SERVICE_TOGGLE_PROFILE = "toggle_profile"