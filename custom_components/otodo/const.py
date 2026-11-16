"""Constants for the otodo integration."""

from datetime import timedelta

DOMAIN = "otodo"

# The URL, API key and verify-SSL keys are Home Assistant's shared ones
# (homeassistant.const), so stored entries keep their "url" and "api_key" keys.
CONF_FINGERPRINT = "fingerprint"

# Server-sent events push every change; polling only catches anything missed
# while the event stream was reconnecting.
FALLBACK_SCAN_INTERVAL = timedelta(minutes=5)
SSE_RECONNECT_DELAY = 30
