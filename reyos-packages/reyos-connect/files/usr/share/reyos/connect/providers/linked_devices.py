"""Explicit, user-initiated KDE-Connect-device <-> Bluetooth-device links.

Never auto-merged on a name-similarity guess (spec: "if identity matching
is uncertain, do not automatically merge devices incorrectly"). A link only
exists here once the user has explicitly chosen it in the "Link Devices"
workflow.
"""
import json
from pathlib import Path

LINKS_PATH = Path.home() / ".config" / "reyos-connect" / "linked-devices.json"


def _load():
    try:
        return json.loads(LINKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data):
    LINKS_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    LINKS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def all_links():
    return _load()


def get_linked_mac(kdeconnect_device_id):
    return _load().get(kdeconnect_device_id)


def link(kdeconnect_device_id, bluetooth_mac):
    data = _load()
    data[kdeconnect_device_id] = bluetooth_mac
    _save(data)


def unlink(kdeconnect_device_id):
    data = _load()
    if data.pop(kdeconnect_device_id, None) is not None:
        _save(data)
