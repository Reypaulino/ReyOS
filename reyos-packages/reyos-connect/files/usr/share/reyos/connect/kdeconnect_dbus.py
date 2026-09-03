"""Thin Qt D-Bus wrapper around the real kdeconnectd daemon.

Every interface/method/property/signal name here was verified against the
actual installed kdeconnectd (26.08.0) -- live introspection of the daemon
object plus the matching v26.08.0 upstream source, cross-checked against
`strings` output of the installed libkdeconnectcore.so. See docs/connect.md
for the full audit. Nothing here is guessed.

This module never touches the network or the pairing/encryption protocol
itself -- kdeconnectd owns all of that. It only calls/listens to D-Bus.
"""
import logging

from PySide6.QtCore import QMetaType, QObject, SLOT, Signal, Slot
from PySide6.QtDBus import (
    QDBusArgument,
    QDBusConnection,
    QDBusInterface,
    QDBusMessage,
    QDBusServiceWatcher,
    QDBusVariant,
)

log = logging.getLogger("reyos-connect.dbus")

SERVICE = "org.kde.kdeconnect"
DAEMON_PATH = "/modules/kdeconnect"
DAEMON_IFACE = "org.kde.kdeconnect.daemon"
DEVICE_IFACE = "org.kde.kdeconnect.device"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def _device_path(device_id):
    return f"{DAEMON_PATH}/devices/{device_id}"


def _unwrap(value):
    # PySide6 auto-converts scalar D-Bus types (bool/int/str) to native
    # python values already, but a variant-typed reply wrapping a
    # compound type (e.g. Properties.Get on an "as" property like
    # customDevices) comes back as an actual QDBusVariant instance --
    # confirmed live (`TypeError: 'QDBusVariant' object is not
    # iterable`). QDBusVariant's accessor is .variant() (returns a
    # QVariant), not .value() -- QDBusVariant has no .value() at all.
    if isinstance(value, QDBusVariant):
        return _unwrap(value.variant())
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        try:
            return value.value()
        except Exception:
            return value
    return value


class DBusCallError(Exception):
    pass


def _call(service, path, iface, method, *args):
    interface = QDBusInterface(service, path, iface, QDBusConnection.sessionBus())
    if not interface.isValid():
        raise DBusCallError(interface.lastError().message() or "invalid D-Bus interface")
    reply = interface.call(method, *args)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise DBusCallError(reply.errorMessage())
    args_out = reply.arguments()
    if not args_out:
        return None
    if len(args_out) == 1:
        return _unwrap(args_out[0])
    return [_unwrap(a) for a in args_out]


def get_property(path, iface, name, default=None):
    try:
        value = _call(SERVICE, path, PROPS_IFACE, "Get", iface, name)
        return default if value is None else _unwrap(value)
    except DBusCallError:
        return default


def set_property(path, iface, name, value):
    _call(SERVICE, path, PROPS_IFACE, "Set", iface, name, QDBusVariant(value))


def _set_stringlist_property(path, iface, name, values):
    values = list(values)
    if values:
        # Plain list marshalling works fine once there's at least one
        # element for Qt to infer the "as" (string array) type from.
        set_property(path, iface, name, values)
        return
    # An empty python list is type-ambiguous to QDBusVariant() -- Qt has
    # no element to infer a signature from. Confirmed live: this raised
    # org.qtproject.QtDBus.Error.InternalError ("Internal error") from
    # kdeconnectd's Properties.Set reply, purely a PySide6/Qt client-side
    # marshalling limitation (not a kdeconnectd bug -- the daemon never
    # even saw a request). Fix: build an explicitly-typed empty QStringList
    # via QDBusArgument instead of relying on type inference.
    arg = QDBusArgument()
    arg.beginArray(QMetaType(QMetaType.Type.QString))
    arg.endArray()
    _call(SERVICE, path, PROPS_IFACE, "Set", iface, name, QDBusVariant(arg))


def daemon_call(method, *args):
    return _call(SERVICE, DAEMON_PATH, DAEMON_IFACE, method, *args)


def get_custom_devices():
    # Bare IP/hostname strings only, no port -- confirmed from v26.08.0
    # source (Daemon::customDevices()/LanLinkProvider::getBroadcastAddresses(),
    # each entry parsed with QHostAddress(entry), not a URL). This is
    # KDE Connect's own answer to "discovery doesn't reach across subnets":
    # setting this property sends a direct (non-broadcast) identity probe
    # to that address too, on top of the normal LAN broadcast.
    return list(get_property(DAEMON_PATH, DAEMON_IFACE, "customDevices", []) or [])


def add_custom_device(ip_address):
    current = get_custom_devices()
    if ip_address not in current:
        current.append(ip_address)
        _set_stringlist_property(DAEMON_PATH, DAEMON_IFACE, "customDevices", current)
        daemon_call("forceOnNetworkChange")


def remove_custom_device(ip_address):
    current = get_custom_devices()
    if ip_address in current:
        current.remove(ip_address)
        _set_stringlist_property(DAEMON_PATH, DAEMON_IFACE, "customDevices", current)


def device_call(device_id, method, *args):
    return _call(SERVICE, _device_path(device_id), DEVICE_IFACE, method, *args)


def plugin_call(device_id, plugin, method, *args):
    iface = f"{DEVICE_IFACE}.{plugin}"
    return _call(SERVICE, _device_path(device_id), iface, method, *args)


def plugin_property(device_id, plugin, name, default=None):
    iface = f"{DEVICE_IFACE}.{plugin}"
    return get_property(_device_path(device_id), iface, name, default)


def device_snapshot(device_id):
    """One real round-trip per field -- called only when a device is added
    or one of its signals fires, never on a timer."""
    path = _device_path(device_id)
    is_paired = bool(get_property(path, DEVICE_IFACE, "isPaired", False))
    is_reachable = bool(get_property(path, DEVICE_IFACE, "isReachable", False))
    is_pair_requested = bool(get_property(path, DEVICE_IFACE, "isPairRequested", False))
    is_pair_requested_by_peer = bool(get_property(path, DEVICE_IFACE, "isPairRequestedByPeer", False))
    # Bare QHostAddress::toString() -- no scheme, no port (confirmed from
    # v26.08.0's LanDeviceLink source, see docs/connect.md). Empty when
    # unreachable, since it's one entry per live link, not a cached value.
    reachable_addresses = get_property(path, DEVICE_IFACE, "reachableAddresses", []) or []
    ip_address = reachable_addresses[0] if reachable_addresses else None

    if is_pair_requested_by_peer:
        state = "pairingIncoming"
    elif is_pair_requested:
        state = "pairingOutgoing"
    elif is_paired and is_reachable:
        state = "connected"
    elif is_paired and not is_reachable:
        state = "disconnected"
    elif is_reachable:
        state = "available"
    else:
        state = "unreachable"

    try:
        loaded_plugins = device_call(device_id, "loadedPlugins") or []
    except DBusCallError:
        loaded_plugins = []

    battery = None
    if "kdeconnect_battery" in loaded_plugins:
        has_battery = plugin_property(device_id, "battery", "hasBattery", False)
        charge = plugin_property(device_id, "battery", "charge", -1)
        if has_battery and charge is not None and charge >= 0:
            battery = {
                "charge": int(charge),
                "isCharging": bool(plugin_property(device_id, "battery", "isCharging", False)),
            }

    return {
        "id": device_id,
        "name": get_property(path, DEVICE_IFACE, "name", device_id),
        "type": get_property(path, DEVICE_IFACE, "type", "unknown"),
        "statusIconName": get_property(path, DEVICE_IFACE, "statusIconName", ""),
        "isPaired": is_paired,
        "isReachable": is_reachable,
        "isPairRequested": is_pair_requested,
        "isPairRequestedByPeer": is_pair_requested_by_peer,
        "state": state,
        "loadedPlugins": list(loaded_plugins),
        "battery": battery,
        "ipAddress": ip_address,
    }


class _DeviceRelay(QObject):
    """QDBusConnection.connect() requires a real QObject + a byte-encoded
    SLOT() signature as the receiver -- it will not take a bare python
    callable (confirmed live: `TypeError: connect expected at least 6
    arguments`). One of these is created per device so its @Slot methods
    can close over device_id and re-emit through plain Qt signals, which
    *do* accept ordinary python callables."""

    stateChanged = Signal(str)
    pairingFailed = Signal(str, str)
    shareReceived = Signal(str, str)
    batteryChanged = Signal(str, bool, int)

    def __init__(self, device_id):
        super().__init__()
        self.device_id = device_id

    @Slot(bool)
    def onReachableChanged(self, _reachable):
        self.stateChanged.emit(self.device_id)

    @Slot(int)
    def onPairStateChanged(self, _state):
        self.stateChanged.emit(self.device_id)

    @Slot()
    def onPluginsChanged(self):
        self.stateChanged.emit(self.device_id)

    @Slot(str)
    def onPairingFailed(self, error):
        self.pairingFailed.emit(self.device_id, error)

    @Slot(str)
    def onShareReceived(self, local_path):
        self.shareReceived.emit(self.device_id, local_path)

    @Slot(bool, int)
    def onBatteryRefreshed(self, is_charging, charge):
        self.batteryChanged.emit(self.device_id, bool(is_charging), int(charge))


class KdeConnectWatcher(QObject):
    """Owns the D-Bus signal subscriptions and re-emits them as Qt signals
    Backend can forward straight into QML. No polling anywhere in here."""

    backendAvailableChanged = Signal(bool)
    deviceAdded = Signal(str)
    deviceRemoved = Signal(str)
    deviceListChanged = Signal()
    deviceStateChanged = Signal(str)   # device id -- something about it changed, re-fetch
    pairingFailed = Signal(str, str)   # device id, error
    shareReceived = Signal(str, str)   # device id, local file path
    batteryChanged = Signal(str, bool, int)  # device id, isCharging, charge

    def __init__(self):
        super().__init__()
        self._bus = QDBusConnection.sessionBus()
        self._watcher = QDBusServiceWatcher(
            SERVICE, self._bus,
            QDBusServiceWatcher.WatchModeFlag.WatchForRegistration
            | QDBusServiceWatcher.WatchModeFlag.WatchForUnregistration,
        )
        self._watcher.serviceRegistered.connect(lambda *_: self._on_backend_up())
        self._watcher.serviceUnregistered.connect(lambda *_: self.backendAvailableChanged.emit(False))
        self._relays = {}
        if self.backend_running():
            self._on_backend_up()

    def backend_running(self):
        return self._bus.interface().isServiceRegistered(SERVICE).value()

    def _on_backend_up(self):
        self._subscribe_daemon()
        self.backendAvailableChanged.emit(True)

    def _subscribe_daemon(self):
        self._bus.connect(SERVICE, DAEMON_PATH, DAEMON_IFACE, "deviceAdded",
                           self, SLOT("_onDeviceAdded(QString)"))
        self._bus.connect(SERVICE, DAEMON_PATH, DAEMON_IFACE, "deviceRemoved",
                           self, SLOT("_onDeviceRemoved(QString)"))
        self._bus.connect(SERVICE, DAEMON_PATH, DAEMON_IFACE, "deviceListChanged",
                           self, SLOT("_onDeviceListChanged()"))
        for device_id in self.list_device_ids():
            self._subscribe_device(device_id)

    @Slot(str)
    def _onDeviceAdded(self, device_id):
        self._subscribe_device(device_id)
        self.deviceAdded.emit(device_id)

    @Slot(str)
    def _onDeviceRemoved(self, device_id):
        self.deviceRemoved.emit(device_id)

    @Slot()
    def _onDeviceListChanged(self):
        self.deviceListChanged.emit()

    def _subscribe_device(self, device_id):
        if device_id in self._relays:
            return
        relay = _DeviceRelay(device_id)
        relay.stateChanged.connect(self.deviceStateChanged.emit)
        relay.pairingFailed.connect(self.pairingFailed.emit)
        relay.shareReceived.connect(self.shareReceived.emit)
        relay.batteryChanged.connect(self.batteryChanged.emit)
        self._relays[device_id] = relay

        path = _device_path(device_id)
        self._bus.connect(SERVICE, path, DEVICE_IFACE, "reachableChanged",
                           relay, SLOT("onReachableChanged(bool)"))
        self._bus.connect(SERVICE, path, DEVICE_IFACE, "pairStateChanged",
                           relay, SLOT("onPairStateChanged(int)"))
        self._bus.connect(SERVICE, path, DEVICE_IFACE, "pluginsChanged",
                           relay, SLOT("onPluginsChanged()"))
        self._bus.connect(SERVICE, path, DEVICE_IFACE, "pairingFailed",
                           relay, SLOT("onPairingFailed(QString)"))
        self._bus.connect(SERVICE, path, f"{DEVICE_IFACE}.share", "shareReceived",
                           relay, SLOT("onShareReceived(QString)"))
        self._bus.connect(SERVICE, path, f"{DEVICE_IFACE}.battery", "refreshed",
                           relay, SLOT("onBatteryRefreshed(bool,int)"))

    def list_device_ids(self):
        try:
            return list(daemon_call("devices", False, False) or [])
        except DBusCallError:
            return []
