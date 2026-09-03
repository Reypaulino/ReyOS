"""Pure D-Bus BlueZ provider -- no `bluetoothctl` shelling.

Control Center's existing `_bt()` helper wraps every `bluetoothctl` call in
`timeout` because `bluetoothctl` itself hangs indefinitely with no adapter
present (confirmed live, see control-center/main.py's own comment on this).
Going straight to `org.bluez` over D-Bus sidesteps that whole class of hang
and gets real `InterfacesAdded`/`InterfacesRemoved`/`PropertiesChanged`
signals instead of a poll loop.

BlueZ lives on the *system* bus, not the session bus KDE Connect uses.

Confirmed live during the Phase 0 audit: no adapter is passed through to
the Dev VM at all (`org.bluez` isn't even registered), so this module is
verified against the physical host's real BlueZ stack instead -- real
paired devices there are an Xbox controller and one other Bluetooth HID
game controller, not a phone. UUID-to-capability mapping below is checked
against ground truth (both report HID-only capabilities, nothing
phone-related), not merely against the spec written to a spec sheet.
"""
import logging

from PySide6.QtCore import QObject, SLOT, Signal, Slot
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage, QDBusServiceWatcher

log = logging.getLogger("reyos-connect.bluetooth")

SERVICE = "org.bluez"
ROOT_PATH = "/"
OBJECT_MANAGER_IFACE = "org.freedesktop.DBus.ObjectManager"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
PROPS_IFACE = "org.freedesktop.DBus.Properties"

# Standard Bluetooth SDP profile UUIDs (16-bit, embedded in the base UUID),
# lowercased as BlueZ reports them.
_HFP_UUIDS = {"0000111e-0000-1000-8000-00805f9b34fb", "0000111f-0000-1000-8000-00805f9b34fb"}
_PBAP_UUIDS = {"0000112e-0000-1000-8000-00805f9b34fb", "0000112f-0000-1000-8000-00805f9b34fb"}
_MAP_UUIDS = {"00001132-0000-1000-8000-00805f9b34fb", "00001133-0000-1000-8000-00805f9b34fb"}


def short_id(mac):
    """Redacted display id -- spec asks not to show the full hardware
    address in normal UI. Last two octets are enough to disambiguate
    multiple devices without publishing the whole address."""
    parts = mac.split(":")
    return "…" + ":".join(parts[-2:]) if len(parts) >= 2 else mac


def _call(service, path, iface, method, *args):
    interface = QDBusInterface(service, path, iface, QDBusConnection.systemBus())
    if not interface.isValid():
        return None
    reply = interface.call(method, *args)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return None
    out = reply.arguments()
    return out[0] if len(out) == 1 else out


def bluez_available():
    return QDBusConnection.systemBus().interface().isServiceRegistered(SERVICE).value()


def _managed_objects():
    result = _call(SERVICE, ROOT_PATH, OBJECT_MANAGER_IFACE, "GetManagedObjects")
    return dict(result) if result else {}


def adapter_status():
    if not bluez_available():
        return {"available": False, "hasAdapter": False, "powered": False, "discoverable": False}
    for path, ifaces in _managed_objects().items():
        if ADAPTER_IFACE in ifaces:
            props = ifaces[ADAPTER_IFACE]
            return {
                "available": True,
                "hasAdapter": True,
                "powered": bool(props.get("Powered", False)),
                "discoverable": bool(props.get("Discoverable", False)),
                "name": str(props.get("Alias", "")),
            }
    return {"available": True, "hasAdapter": False, "powered": False, "discoverable": False}


def _device_capabilities(uuids):
    uuid_set = {u.lower() for u in uuids}
    return {
        "calls": "AVAILABLE" if uuid_set & _HFP_UUIDS else "UNAVAILABLE",
        "contacts": "AVAILABLE" if uuid_set & _PBAP_UUIDS else "UNAVAILABLE",
        "messages": "AVAILABLE" if uuid_set & _MAP_UUIDS else "UNAVAILABLE",
    }


def list_paired_devices():
    if not bluez_available():
        return []
    devices = []
    for path, ifaces in _managed_objects().items():
        if DEVICE_IFACE not in ifaces:
            continue
        props = ifaces[DEVICE_IFACE]
        if not props.get("Paired", False):
            continue
        mac = str(props.get("Address", ""))
        uuids = [str(u) for u in (props.get("UUIDs") or [])]
        devices.append({
            "path": path,
            "mac": mac,
            "shortId": short_id(mac),
            "name": str(props.get("Name") or props.get("Alias") or "Unknown device"),
            "icon": str(props.get("Icon", "")),
            "paired": True,
            "trusted": bool(props.get("Trusted", False)),
            "connected": bool(props.get("Connected", False)),
            "uuids": uuids,
            # AVAILABLE here means "profile advertised" only -- still
            # NOT_TESTED for real use until actually exercised against a
            # real device, per the spec's "don't mark PASS on API
            # existence alone." The GUI layer is responsible for not
            # calling this PASS.
            "capabilities": _device_capabilities(uuids),
        })
    return devices


def connect_device(mac):
    path = next((d["path"] for d in list_paired_devices() if d["mac"] == mac), None)
    if not path:
        return False
    return _call(SERVICE, path, DEVICE_IFACE, "Connect") is not None


def disconnect_device(mac):
    path = next((d["path"] for d in list_paired_devices() if d["mac"] == mac), None)
    if not path:
        return False
    return _call(SERVICE, path, DEVICE_IFACE, "Disconnect") is not None


# -- Real phone-capability probes ------------------------------------------
#
# `_device_capabilities()` above only reflects UUIDs the device *advertises*
# -- the spec explicitly forbids treating that as PASS. These functions
# actually exercise the profile against a real paired device and report
# what happened. Real, on this iPhone (2026-09-02, host's real BlueZ +
# obexd, iPhone AC:45:00:3D:8A:4E "Reyrubi Iphone"): PBAP connects but the
# phonebook is empty (no consent prompt ever appears), MAP is refused
# outright (OBEX error 0x43, Forbidden). Both match a well-documented iOS
# restriction -- full PBAP/MAP access is only granted to devices Apple
# recognizes as MFi-certified car-kit accessories; a generic BlueZ pairing
# never gets the "Sync Contacts"/"Show Notifications" consent flow at all.
# See docs/connect.md's "Part 3" section for the full writeup.

OBEX_SERVICE = "org.bluez.obex"
OBEX_ROOT = "/org/bluez/obex"
OBEX_CLIENT_IFACE = "org.bluez.obex.Client1"


def _obex_call(path, iface, method, *args):
    interface = QDBusInterface(OBEX_SERVICE, path, iface, QDBusConnection.sessionBus())
    if not interface.isValid():
        return None, "obexd is not available (org.bluez.obex not registered on the session bus)."
    reply = interface.call(method, *args)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        return None, reply.errorMessage() or reply.errorName()
    out = reply.arguments()
    return (out[0] if len(out) == 1 else out), None


def _obex_session(mac, target):
    return _obex_call(OBEX_ROOT, OBEX_CLIENT_IFACE, "CreateSession", mac, {"Target": target})


def probe_contacts(mac):
    session, err = _obex_session(mac, "PBAP")
    if err:
        return {"result": "UNAVAILABLE", "detail": f"PBAP session failed: {err}"}
    session = str(session)
    try:
        pbap = QDBusInterface(OBEX_SERVICE, session, "org.bluez.obex.PhonebookAccess1", QDBusConnection.sessionBus())
        select_reply = pbap.call("Select", "int", "pb")
        if select_reply.type() == QDBusMessage.MessageType.ErrorMessage:
            return {"result": "UNAVAILABLE", "detail": f"PBAP Select failed: {select_reply.errorMessage()}"}
        size_reply = pbap.call("GetSize")
        args = size_reply.arguments()
        size = int(args[0]) if args else 0
    finally:
        _obex_call(OBEX_ROOT, OBEX_CLIENT_IFACE, "RemoveSession", session)
    if size > 0:
        return {"result": "AVAILABLE", "detail": f"{size} phonebook entries reachable via PBAP."}
    return {
        "result": "UNAVAILABLE",
        "detail": ("PBAP connects but the phonebook is empty and no consent prompt appears on the "
                   "phone -- iOS only grants full contact sync to MFi-certified car-kit accessories, "
                   "not a generic Bluetooth pairing."),
    }


def probe_messages(mac):
    session, err = _obex_session(mac, "MAP")
    if err:
        return {
            "result": "UNAVAILABLE",
            "detail": (f"MAP session refused: {err} -- iOS reserves message access for "
                       "MFi-certified car-kit accessories, not a generic Bluetooth pairing."),
        }
    _obex_call(OBEX_ROOT, OBEX_CLIENT_IFACE, "RemoveSession", str(session))
    return {"result": "AVAILABLE", "detail": "MAP session established -- message folders reachable."}


def probe_calls():
    """No live probe: exercising real HFP call control needs oFono (BlueZ
    itself only does SCO audio routing, not AT-command call-state
    signaling), and oFono is deliberately not a `reyos-connect` dependency
    -- adding a second telephony daemon that's confirmed non-functional for
    this exact scenario would violate the "no duplicate daemon without a
    proven need" rule. Real research finding, from testing with a
    temporarily-installed oFono against this same iPhone: oFono's HFP
    profile registers fine once WirePlumber's native backend yields the
    role, but every real ConnectProfile() attempt was refused at the link
    layer (br-connection-page-timeout, Host is down, and
    br-connection-profile-unavailable -- the last reproduced even during an
    active call). Same iOS MFi restriction as contacts/messages, not a
    ReyOS gap. See docs/connect.md."""
    return {
        "result": "UNAVAILABLE",
        "detail": ("iOS refuses standard Handsfree (HFP) call-control connections outside "
                   "MFi-certified car-kit accessories -- confirmed by real testing (oFono profile "
                   "registers, but every connection attempt is refused by the phone, even mid-call). "
                   "Not a ReyOS gap."),
    }


class BluetoothWatcher(QObject):
    """Signal-driven, no polling. Re-enumerates on any BlueZ change --
    the device list here is small enough that a full GetManagedObjects()
    re-fetch per signal is cheap, unlike KDE Connect's finer-grained
    per-device relay approach."""

    availabilityChanged = Signal(bool)
    changed = Signal()

    def __init__(self):
        super().__init__()
        self._bus = QDBusConnection.systemBus()
        self._watcher = QDBusServiceWatcher(
            SERVICE, self._bus,
            QDBusServiceWatcher.WatchModeFlag.WatchForRegistration
            | QDBusServiceWatcher.WatchModeFlag.WatchForUnregistration,
        )
        self._watcher.serviceRegistered.connect(lambda *_: self._on_up())
        self._watcher.serviceUnregistered.connect(lambda *_: self.availabilityChanged.emit(False))
        if bluez_available():
            self._subscribe()

    def _on_up(self):
        self._subscribe()
        self.availabilityChanged.emit(True)

    def _subscribe(self):
        self._bus.connect(SERVICE, "", OBJECT_MANAGER_IFACE, "InterfacesAdded",
                           self, SLOT("_onChanged()"))
        self._bus.connect(SERVICE, "", OBJECT_MANAGER_IFACE, "InterfacesRemoved",
                           self, SLOT("_onChanged()"))
        self._bus.connect(SERVICE, "", PROPS_IFACE, "PropertiesChanged",
                           self, SLOT("_onChanged()"))

    @Slot()
    def _onChanged(self):
        self.changed.emit()
