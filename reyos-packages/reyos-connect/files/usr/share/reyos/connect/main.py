#!/usr/bin/env python3
import logging
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import QObject, QProcess, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

import kdeconnect_dbus as kdc
from providers import bluetooth_provider as bt
from providers import linked_devices
from providers import remote_provider
from providers import vpn_provider

LOG_DIR = Path.home() / ".cache" / "reyos-connect"
LOG_FILE = LOG_DIR / "reyos-connect.log"


def _setup_logging():
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


log = logging.getLogger("reyos-connect")


def _notify(title, message):
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "-a", "ReyOS Connect", "-i", "org.reyos.Connect", title, message],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


class ActionWorker(QThread):
    finished_ok = Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            ok, message = self.fn()
            self.finished_ok.emit(ok, message)
        except kdc.DBusCallError as e:
            self.finished_ok.emit(False, str(e))
        except Exception as e:
            log.exception("action failed")
            self.finished_ok.emit(False, str(e))


class InfoWorker(QThread):
    """Runs a blocking read-only fetch off the UI thread and emits its
    result once. Mirrors control-center's own InfoWorker/ListWorker
    convention (separate process/package, not shared code)."""
    ready = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.ready.emit(self.fn())
        except Exception:
            log.exception("info fetch failed")
            self.ready.emit(None)


class Backend(QObject):
    backendAvailableChanged = Signal(bool)
    devicesChanged = Signal()
    pairingFailedSignal = Signal(str, str)     # deviceId, error
    fileReceived = Signal(str, str)            # deviceId, localPath
    actionFinished = Signal(bool, str)
    diagnosticsReady = Signal("QVariantMap")
    vpnStatusReady = Signal("QVariantMap")
    remoteConnectionTestReady = Signal("QVariantMap")
    bluetoothStatusReady = Signal("QVariantMap")
    phoneCapabilitiesReady = Signal(str, "QVariantMap")  # mac, {contacts, messages, calls}
    connectionDiagnosticsReady = Signal("QVariantList")
    remoteCommandsReady = Signal("QVariantList")

    def __init__(self):
        super().__init__()
        self._watcher = kdc.KdeConnectWatcher()
        self._watcher.backendAvailableChanged.connect(self.backendAvailableChanged.emit)
        self._watcher.deviceAdded.connect(lambda *_: self.devicesChanged.emit())
        self._watcher.deviceRemoved.connect(lambda *_: self.devicesChanged.emit())
        self._watcher.deviceListChanged.connect(self.devicesChanged.emit)
        self._watcher.deviceStateChanged.connect(lambda *_: self.devicesChanged.emit())
        self._watcher.pairingFailed.connect(self.pairingFailedSignal.emit)
        self._watcher.shareReceived.connect(self._on_share_received)
        self._watcher.batteryChanged.connect(lambda *_: self.devicesChanged.emit())
        self._bt_watcher = bt.BluetoothWatcher()
        self._bt_watcher.availabilityChanged.connect(lambda *_: self.refreshBluetoothStatus())
        self._bt_watcher.changed.connect(self.refreshBluetoothStatus)
        self._workers = []
        self._known_ids = set(self._watcher.list_device_ids())

    def _on_share_received(self, device_id, local_path):
        name = kdc.get_property(kdc._device_path(device_id), kdc.DEVICE_IFACE, "name", device_id)
        _notify(f"File received from {name}", Path(local_path).name)
        self.fileReceived.emit(device_id, local_path)

    def _run(self, fn):
        worker = ActionWorker(fn)
        worker.finished_ok.connect(self.actionFinished.emit)
        # Pairing/unpair D-Bus calls don't reliably produce a *timely*
        # pairStateChanged signal back on this end (confirmed live: a
        # successful acceptPairing()/cancelPairing() call left the device
        # card showing stale pre-action state because nothing else told
        # QML to re-fetch it) -- refresh proactively once our own action
        # finishes rather than only reacting to the daemon's own signals.
        worker.finished_ok.connect(lambda *_: self.devicesChanged.emit())
        worker.finished_ok.connect(lambda *_: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    # -- installation / daemon state -----------------------------------

    @Slot(result=bool)
    def isKdeconnectInstalled(self):
        return shutil.which("kdeconnectd") is not None

    @Slot(result=bool)
    def isDaemonRunning(self):
        return self._watcher.backend_running()

    @Slot()
    def startDaemon(self):
        if not self.isKdeconnectInstalled():
            self.actionFinished.emit(False, "KDE Connect is not installed.")
            return
        ok = QProcess.startDetached("/usr/bin/kdeconnectd", [])
        if ok:
            QTimer.singleShot(1500, self.devicesChanged.emit)
            self.actionFinished.emit(True, "Starting KDE Connect...")
        else:
            self.actionFinished.emit(False, "Could not start the KDE Connect background service.")

    @Slot()
    def refreshDiagnostics(self):
        def task():
            installed = self.isKdeconnectInstalled()
            running = self._watcher.backend_running()
            self_id = ""
            self_name = ""
            if running:
                try:
                    self_id = kdc.daemon_call("selfId") or ""
                    self_name = kdc.daemon_call("announcedName") or ""
                except kdc.DBusCallError:
                    pass
            fw_open = None
            fw_detail = "Could not check firewall status."
            try:
                result = subprocess.run(
                    ["sudo", "-n", "ufw", "status"], capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    out = result.stdout
                    if "inactive" in out.lower():
                        fw_open = True
                        fw_detail = "Firewall is inactive -- KDE Connect's ports are not blocked."
                    elif "1714:1764" in out or "KDEConnect" in out or "KDE Connect" in out:
                        fw_open = True
                        fw_detail = "Firewall is active and KDE Connect's ports (1714-1764) are allowed."
                    else:
                        fw_open = False
                        fw_detail = "Firewall is active and KDE Connect's ports do not look open yet."
            except Exception:
                pass
            info = {
                "installed": installed,
                "daemonRunning": running,
                "selfId": self_id,
                "selfName": self_name,
                "firewallOpen": fw_open,
                "firewallDetail": fw_detail,
            }
            self.diagnosticsReady.emit(info)
        task()

    @Slot()
    def openFirewallForKdeConnect(self):
        def task():
            result = subprocess.run(
                ["sudo", "ufw", "allow", "KDEConnect"], capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return True, "KDE Connect's ports (1714-1764) are now allowed through the firewall."
            return False, (result.stderr.strip() or "Could not update the firewall.")
        self._run(task)

    # -- device list / detail -------------------------------------------

    @Slot(result="QVariantList")
    def listDevices(self):
        if not self._watcher.backend_running():
            return []
        return [kdc.device_snapshot(d) for d in self._watcher.list_device_ids()]

    # -- connect by IP (crosses subnets/hotspots broadcast can't reach) ---

    @Slot(result="QVariantList")
    def listCustomDevices(self):
        return kdc.get_custom_devices()

    @Slot(str)
    def addCustomDevice(self, ip_address):
        def task():
            from PySide6.QtNetwork import QHostAddress

            ip = ip_address.strip()
            if not ip:
                return False, "Enter an IP address first."
            if QHostAddress(ip).isNull():
                return False, f'"{ip}" is not a valid IP address.'
            if ip in kdc.get_custom_devices():
                return False, "That address is already added."
            kdc.add_custom_device(ip)
            return True, f"Added {ip} -- looking for a device there now."
        self._run(task)

    @Slot(str)
    def removeCustomDevice(self, ip_address):
        def task():
            kdc.remove_custom_device(ip_address)
            return True, f"Removed {ip_address}."
        self._run(task)

    @Slot(str, result="QVariantMap")
    def deviceDetail(self, device_id):
        snap = kdc.device_snapshot(device_id)
        plugins = snap["loadedPlugins"]
        remote_keyboard_active = None
        if "kdeconnect_remotekeyboard" in plugins:
            remote_keyboard_active = bool(kdc.plugin_property(device_id, "remotekeyboard", "remoteState", False))
        clipboard_auto_disabled = None
        if "kdeconnect_clipboard" in plugins:
            clipboard_auto_disabled = bool(kdc.plugin_property(device_id, "clipboard", "isAutoShareDisabled", False))
        snap.update({
            "canFindMyPhone": "kdeconnect_findmyphone" in plugins,
            "canPing": "kdeconnect_ping" in plugins,
            "canShare": "kdeconnect_share" in plugins,
            "canClipboard": "kdeconnect_clipboard" in plugins,
            "clipboardAutoDisabled": clipboard_auto_disabled,
            "canRemoteKeyboard": "kdeconnect_remotekeyboard" in plugins,
            "remoteKeyboardActive": remote_keyboard_active,
            "canRunCommand": "kdeconnect_runcommand" in plugins,
        })
        return snap

    # -- pairing ----------------------------------------------------------

    @Slot(str)
    def requestPairing(self, device_id):
        def task():
            kdc.device_call(device_id, "requestPairing")
            return True, "Pairing request sent. Approve it on your phone."
        self._run(task)

    @Slot(str)
    def acceptPairing(self, device_id):
        def task():
            kdc.device_call(device_id, "acceptPairing")
            return True, "Device paired."
        self._run(task)

    @Slot(str)
    def rejectPairing(self, device_id):
        def task():
            kdc.device_call(device_id, "cancelPairing")
            return True, "Pairing request dismissed."
        self._run(task)

    @Slot(str)
    def unpairDevice(self, device_id):
        def task():
            kdc.device_call(device_id, "unpair")
            return True, "Device unpaired."
        self._run(task)

    # -- plugin actions -----------------------------------------------------

    @Slot(str)
    def ringDevice(self, device_id):
        def task():
            kdc.plugin_call(device_id, "findmyphone", "ring")
            return True, "Ringing device."
        self._run(task)

    @Slot(str)
    def pingDevice(self, device_id):
        def task():
            kdc.plugin_call(device_id, "ping", "sendPing")
            return True, "Ping sent."
        self._run(task)

    @Slot(str, str)
    def sendUrlToDevice(self, device_id, url):
        def task():
            if not url.strip():
                return False, "Enter a link first."
            kdc.plugin_call(device_id, "share", "shareUrl", url.strip())
            return True, "Link sent."
        self._run(task)

    @Slot(str)
    def sendClipboardToDevice(self, device_id):
        def task():
            kdc.plugin_call(device_id, "clipboard", "sendClipboard")
            return True, "Clipboard sent."
        self._run(task)

    @Slot(str)
    def openFilePickerAndSend(self, device_id):
        from PySide6.QtWidgets import QFileDialog

        paths, _filter = QFileDialog.getOpenFileNames(None, "Send File", str(Path.home()))
        if not paths:
            return
        self.sendFilesToDevice(device_id, paths)

    @Slot(str, "QVariantList")
    def sendFilesToDevice(self, device_id, local_paths):
        def task():
            urls = [QUrl.fromLocalFile(p).toString() for p in local_paths]
            if len(urls) == 1:
                kdc.plugin_call(device_id, "share", "shareUrl", urls[0])
            else:
                kdc.plugin_call(device_id, "share", "shareUrls", urls)
            noun = "file" if len(urls) == 1 else f"{len(urls)} files"
            return True, f"Sending {noun}..."
        self._run(task)

    @Slot(str)
    def openRemoteCommandsConfig(self, device_id):
        # RunCommand has no D-Bus config API (confirmed from source, see
        # docs/connect.md) -- commands are a local JSON blob only KDE
        # Connect's own app is allowed to write, so ReyOS Connect launches
        # it rather than hand-writing that file's serialization format.
        if shutil.which("kdeconnect-app"):
            QProcess.startDetached("kdeconnect-app", [])
        else:
            self.actionFinished.emit(False, "kdeconnect-app is not installed.")

    @Slot(str)
    def openContainingFolder(self, local_path):
        folder = str(Path(local_path).expanduser().parent)
        subprocess.Popen(["xdg-open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -- Remote Access (VPN) ---------------------------------------------

    @Slot()
    def refreshVpnStatus(self):
        def fetch():
            return {
                "backends": vpn_provider.detect_backends(),
                "tailscale": vpn_provider.tailscale_status(),
                "wireguard": vpn_provider.wireguard_status(),
            }
        self._vpn_worker = InfoWorker(fetch)
        self._vpn_worker.ready.connect(lambda info: self.vpnStatusReady.emit(info or {}))
        self._vpn_worker.start()

    @Slot(bool)
    def setTailscaleConnected(self, connect):
        self._run(lambda: vpn_provider.tailscale_set_connected(connect))

    @Slot(str, str)
    def connectWireguard(self, name, source):
        self._run(lambda: vpn_provider.wireguard_connect(name, source))

    @Slot(str, str)
    def disconnectWireguard(self, name, source):
        self._run(lambda: vpn_provider.wireguard_disconnect(name, source))

    @Slot(str, str, bool)
    def testRemoteConnection(self, backend, peer_ip, check_ssh):
        def fetch():
            return vpn_provider.test_remote_connection(backend, peer_ip=peer_ip or None, check_ssh=check_ssh)
        self._remote_test_worker = InfoWorker(fetch)
        self._remote_test_worker.ready.connect(lambda info: self.remoteConnectionTestReady.emit(info or {}))
        self._remote_test_worker.start()

    @Slot()
    def openControlCenter(self):
        QProcess.startDetached("/usr/share/reyos/control-center/main.py", [])

    # -- Remote Commands (fixed, safe registry -- no free-text field) ----

    @Slot(str, result="QVariantList")
    def listRemoteCommands(self, device_id):
        enabled = set(remote_provider.read_enabled_commands(device_id))
        return [
            {"id": cmd_id, "name": spec["name"], "enabled": cmd_id in enabled}
            for cmd_id, spec in remote_provider.REMOTE_COMMANDS.items()
        ]

    @Slot(str, str, bool)
    def setRemoteCommandEnabled(self, device_id, cmd_id, enabled):
        def task():
            current = set(remote_provider.read_enabled_commands(device_id))
            if enabled:
                current.add(cmd_id)
            else:
                current.discard(cmd_id)
            ok = remote_provider.write_enabled_commands(device_id, current)
            return ok, ("Updated remote commands." if ok else "Failed to update remote commands.")
        self._run(task)

    @Slot(result="QVariantMap")
    def sshStatus(self):
        return remote_provider.ssh_status()

    @Slot(result="QVariantMap")
    def sshConnectionInfo(self):
        return remote_provider.ssh_connection_info()

    @Slot(result="QVariantMap")
    def remoteDesktopStatus(self):
        return remote_provider.remote_desktop_status()

    @Slot()
    def openRemoteDesktopSettings(self):
        remote_provider.open_remote_desktop_settings()

    @Slot()
    def startRemoteDesktop(self):
        def task():
            ok, err = remote_provider.start_remote_desktop()
            return ok, ("Remote Desktop session started." if ok else f"Failed to start: {err}")
        self._run(task)

    @Slot()
    def stopRemoteDesktop(self):
        def task():
            ok, err = remote_provider.stop_remote_desktop()
            return ok, ("Remote Desktop session stopped." if ok else f"Failed to stop: {err}")
        self._run(task)

    # -- Bluetooth ----------------------------------------------------------

    @Slot(result="QVariantList")
    def listBluetoothDevicesSync(self):
        return bt.list_paired_devices()

    @Slot()
    def refreshBluetoothStatus(self):
        def fetch():
            return {"adapter": bt.adapter_status(), "devices": bt.list_paired_devices()}
        self._bt_status_worker = InfoWorker(fetch)
        self._bt_status_worker.ready.connect(lambda info: self.bluetoothStatusReady.emit(info or {}))
        self._bt_status_worker.start()

    @Slot(str)
    def connectBluetoothDevice(self, mac):
        def task():
            ok = bt.connect_device(mac)
            return ok, ("Connected." if ok else "Failed to connect.")
        self._run(task)

    @Slot(str)
    def disconnectBluetoothDevice(self, mac):
        def task():
            ok = bt.disconnect_device(mac)
            return ok, ("Disconnected." if ok else "Failed to disconnect.")
        self._run(task)

    @Slot(str)
    def probePhoneCapabilities(self, mac):
        """Actually exercises PBAP/MAP against the given paired device (real
        D-Bus round trip, a couple seconds) instead of trusting advertised
        UUIDs -- see bluetooth_provider.probe_*()."""
        def fetch():
            return {
                "contacts": bt.probe_contacts(mac),
                "messages": bt.probe_messages(mac),
                "calls": bt.probe_calls(),
            }
        worker = InfoWorker(fetch)
        worker.ready.connect(lambda result: self.phoneCapabilitiesReady.emit(mac, result or {}))
        worker.ready.connect(lambda *_: self._workers.remove(worker) if worker in self._workers else None)
        self._workers.append(worker)
        worker.start()

    # -- Linked devices (Wi-Fi/Bluetooth/VPN identity merge) ----------------

    @Slot(str, result="QVariantMap")
    def linkedBluetoothInfo(self, device_id):
        mac = linked_devices.get_linked_mac(device_id)
        if not mac:
            return {}
        match = next((d for d in bt.list_paired_devices() if d["mac"] == mac), None)
        if match is None:
            return {"mac": mac, "name": "", "connected": False, "found": False}
        match = dict(match)
        match["found"] = True
        return match

    @Slot(str, str)
    def linkBluetoothDevice(self, device_id, mac):
        linked_devices.link(device_id, mac)
        self.devicesChanged.emit()

    @Slot(str)
    def unlinkBluetoothDevice(self, device_id):
        linked_devices.unlink(device_id)
        self.devicesChanged.emit()

    # -- Connection Diagnostics ----------------------------------------------

    @Slot()
    def refreshConnectionDiagnostics(self):
        def fetch():
            rows = []

            kdc_running = self._watcher.backend_running()
            rows.append({"check": "KDE Connect", "result": "PASS" if kdc_running else "FAIL",
                         "detail": "Daemon is running." if kdc_running else "kdeconnectd is not running."})

            adapter = bt.adapter_status()
            rows.append({"check": "BlueZ", "result": "PASS" if adapter["available"] else "FAIL",
                         "detail": "bluetoothd is reachable over D-Bus." if adapter["available"] else "org.bluez is not registered."})
            rows.append({"check": "Bluetooth", "result": "PASS" if adapter["hasAdapter"] else "FAIL",
                         "detail": "Adapter present." if adapter["hasAdapter"] else "No Bluetooth adapter found."})

            devices = bt.list_paired_devices() if adapter["available"] else []
            iphone = next((d for d in devices if "iphone" in d["name"].lower()), None)
            rows.append({"check": "iPhone Pairing", "result": "PASS" if iphone else "NOT_TESTED",
                         "detail": f"{iphone['name']} is paired." if iphone else "No iPhone Bluetooth-paired yet."})

            backends = vpn_provider.detect_backends()
            vpn_connected = False
            if backends["tailscale"]:
                vpn_connected = vpn_provider.tailscale_status()["connected"]
            elif backends["wireguard"]:
                vpn_connected = bool(vpn_provider.wireguard_status()["active"])
            has_backend = backends["tailscale"] or backends["wireguard"]
            rows.append({
                "check": "VPN",
                "result": "PASS" if vpn_connected else ("NOT_TESTED" if not has_backend else "FAIL"),
                "detail": "VPN connected." if vpn_connected else ("No VPN backend installed." if not has_backend else "No VPN backend connected."),
            })

            if backends["tailscale"]:
                remote = vpn_provider.test_remote_connection("tailscale")
                failing = [c["detail"] for c in remote["checks"] if not c["passed"]]
                rows.append({"check": "Remote Route", "result": "PASS" if remote["ready"] else "FAIL",
                             "detail": "All checks passed." if remote["ready"] else "; ".join(failing)})
            else:
                rows.append({"check": "Remote Route", "result": "NOT_TESTED", "detail": "No VPN backend configured."})

            if iphone:
                contacts = bt.probe_contacts(iphone["mac"])
                messages = bt.probe_messages(iphone["mac"])
                calls = bt.probe_calls()
                rows.append({"check": "Contacts", "result": contacts["result"], "detail": contacts["detail"]})
                rows.append({"check": "Messages", "result": messages["result"], "detail": messages["detail"]})
                rows.append({"check": "Calls", "result": calls["result"], "detail": calls["detail"]})
            else:
                rows.append({"check": "Contacts", "result": "NOT_TESTED", "detail": "Requires a real Bluetooth-paired iPhone."})
                rows.append({"check": "Messages", "result": "NOT_TESTED", "detail": "Requires a real Bluetooth-paired iPhone."})
                rows.append({"check": "Calls", "result": "NOT_TESTED", "detail": "Requires a real Bluetooth-paired iPhone."})

            sshd = remote_provider.ssh_status()
            rows.append({"check": "SSH", "result": "PASS" if sshd["active"] else "NOT_TESTED",
                         "detail": "sshd is active." if sshd["active"] else "sshd is not enabled."})

            fw_open = None
            try:
                fw_result = subprocess.run(["sudo", "-n", "ufw", "status"], capture_output=True, text=True, timeout=10)
                if fw_result.returncode == 0:
                    out = fw_result.stdout
                    if "inactive" in out.lower():
                        fw_open = True
                    elif "1714:1764" in out or "KDEConnect" in out:
                        fw_open = True
                    else:
                        fw_open = False
            except Exception:
                pass
            rows.append({
                "check": "Firewall",
                "result": "PASS" if fw_open else ("NOT_TESTED" if fw_open is None else "FAIL"),
                "detail": "KDE Connect ports allowed (or firewall inactive)." if fw_open else "KDE Connect ports may be blocked.",
            })
            return rows

        self._diag_worker = InfoWorker(fetch)
        self._diag_worker.ready.connect(lambda rows: self.connectionDiagnosticsReady.emit(rows or []))
        self._diag_worker.start()


def main():
    _setup_logging()
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Connect")
    app.setDesktopFileName("org.reyos.Connect")
    app.setOrganizationName("ReyOS")

    engine = QQmlApplicationEngine()
    backend = Backend()
    engine.rootContext().setContextProperty("backend", backend)

    engine.load(QUrl.fromLocalFile(str(APP_DIR / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1

    window = engine.rootObjects()[0]
    window.setIcon(QIcon.fromTheme("org.reyos.Connect"))

    def try_activate(remaining=6):
        window.raise_()
        window.requestActivate()
        if remaining > 0:
            QTimer.singleShot(300, lambda: try_activate(remaining - 1))

    QTimer.singleShot(200, try_activate)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
