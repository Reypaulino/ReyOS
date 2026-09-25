"""Shared capability/state vocabulary. Plain string constants, not a Python
enum -- everything here crosses into QML as plain dict values, matching the
rest of this codebase's convention (kdeconnect_dbus.device_snapshot()'s
"state" field, etc).
"""

FILES = "files"
CLIPBOARD = "clipboard"
SEND_LINK = "send_link"
REMOTE_INPUT = "remote_input"
REMOTE_DESKTOP = "remote_desktop"
SSH = "ssh"
BATTERY = "battery"
CONTACTS = "contacts"
CALLS = "calls"
MESSAGES = "messages"
VPN = "vpn"
BLUETOOTH = "bluetooth"

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"
NOT_TESTED = "NOT_TESTED"
ERROR = "ERROR"

# Sync folder / migration job states (spec's "Status" section) -- distinct
# from the AVAILABLE/UNAVAILABLE capability-detection vocabulary above,
# since a folder can be UP_TO_DATE one minute and SYNCING the next without
# the underlying capability ever having changed.
UP_TO_DATE = "UP_TO_DATE"
SYNCING = "SYNCING"
PAUSED = "PAUSED"
OFFLINE = "OFFLINE"
CONFLICT = "CONFLICT"
SYNC_ERROR = "SYNC_ERROR"
NOT_CONFIGURED = "NOT_CONFIGURED"
