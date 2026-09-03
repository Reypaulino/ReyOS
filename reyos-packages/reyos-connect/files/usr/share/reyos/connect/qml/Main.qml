import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Connect"
    width: 760
    height: 640
    minimumWidth: 480
    minimumHeight: 480

    ListModel { id: deviceModel }
    ListModel { id: customDeviceModel }

    property bool backendAvailable: false
    property bool kdeconnectInstalled: true
    property var diagnostics: ({})

    function refreshDevices() {
        var devices = backend.listDevices()
        deviceModel.clear()
        for (var i = 0; i < devices.length; i++) deviceModel.append(devices[i])
    }

    function refreshCustomDevices() {
        var addrs = backend.listCustomDevices()
        customDeviceModel.clear()
        for (var i = 0; i < addrs.length; i++) customDeviceModel.append({address: addrs[i]})
    }

    function stateLabel(state) {
        switch (state) {
            case "available": return "Available"
            case "pairingOutgoing": return "Pairing…"
            case "pairingIncoming": return "Wants to pair"
            case "connected": return "Connected"
            case "disconnected": return "Paired · Disconnected"
            case "unreachable": return "Unreachable"
            default: return state
        }
    }

    Connections {
        target: backend
        function onBackendAvailableChanged(available) {
            backendAvailable = available
            if (available) refreshDevices()
        }
        function onDevicesChanged() { refreshDevices(); refreshCustomDevices() }
        function onDiagnosticsReady(info) { diagnostics = info }
        function onActionFinished(ok, message) {
            statusBanner.text = message
            statusBanner.type = ok ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            statusBanner.visible = true
            bannerTimer.restart()
        }
        function onPairingFailedSignal(deviceId, error) {
            statusBanner.text = "Pairing failed: " + error
            statusBanner.type = Kirigami.MessageType.Error
            statusBanner.visible = true
            bannerTimer.restart()
        }
        function onFileReceived(deviceId, path) {
            receivedBanner.filePath = path
            receivedBanner.visible = true
        }
    }

    Timer { id: bannerTimer; interval: 6000; onTriggered: statusBanner.visible = false }

    Component.onCompleted: {
        kdeconnectInstalled = backend.isKdeconnectInstalled()
        backendAvailable = backend.isDaemonRunning()
        if (backendAvailable) { refreshDevices(); refreshCustomDevices() }
    }

    function goHome() { while (pageStack.depth > 1) pageStack.pop() }
    function navigateTo(url) { goHome(); pageStack.push(url) }

    globalDrawer: Kirigami.GlobalDrawer {
        title: "ReyOS Connect"
        titleIcon: "org.reyos.Connect"
        isMenu: false
        actions: [
            Kirigami.Action { text: "Dashboard"; icon.name: "go-home"; onTriggered: goHome() },
            Kirigami.Action { text: "Remote Access"; icon.name: "network-vpn"; onTriggered: navigateTo(Qt.resolvedUrl("RemoteAccessPage.qml")) },
            Kirigami.Action { text: "Bluetooth"; icon.name: "preferences-system-bluetooth"; onTriggered: navigateTo(Qt.resolvedUrl("BluetoothPage.qml")) },
            Kirigami.Action { text: "Diagnostics"; icon.name: "diagnostics"; onTriggered: navigateTo(Qt.resolvedUrl("DiagnosticsPage.qml")) }
        ]
    }

    pageStack.initialPage: Kirigami.ScrollablePage {
        title: "ReyOS Connect"
        actions: [
            Kirigami.Action { text: "Menu"; icon.name: "application-menu"; onTriggered: globalDrawer.open() },
            Kirigami.Action {
                text: "Refresh"
                icon.name: "view-refresh"
                enabled: backendAvailable
                onTriggered: { backend.refreshDiagnostics(); if (backendAvailable) refreshDevices() }
            }
        ]

        ColumnLayout {
            width: parent.width
            spacing: Kirigami.Units.largeSpacing

            Kirigami.InlineMessage {
                id: statusBanner
                Layout.fillWidth: true
                visible: false
                showCloseButton: true
            }

            Kirigami.InlineMessage {
                id: receivedBanner
                property string filePath: ""
                Layout.fillWidth: true
                visible: false
                showCloseButton: true
                type: Kirigami.MessageType.Positive
                text: "Received " + (filePath.split("/").pop() || "")
                actions: [
                    Kirigami.Action {
                        text: "Open Folder"
                        onTriggered: backend.openContainingFolder(receivedBanner.filePath)
                    }
                ]
            }

            // -- KDE Connect missing entirely --------------------------------
            Kirigami.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.gridUnit * 3
                visible: !kdeconnectInstalled
                icon.name: "dialog-warning"
                text: "KDE Connect is required for ReyOS Connect."
                explanation: "The kdeconnect package could not be found. Reinstall reyos-connect to pull it back in."
            }

            // -- Installed but the daemon isn't running ----------------------
            Kirigami.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.gridUnit * 3
                visible: kdeconnectInstalled && !backendAvailable
                icon.name: "network-disconnect"
                text: "KDE Connect isn't running"
                explanation: "It normally starts automatically when you log in."
                helpfulAction: Kirigami.Action {
                    text: "Start KDE Connect"
                    icon.name: "media-playback-start"
                    onTriggered: backend.startDaemon()
                }
            }

            // -- Dashboard -----------------------------------------------------
            ColumnLayout {
                Layout.fillWidth: true
                visible: kdeconnectInstalled && backendAvailable
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Heading { text: "Nearby Devices"; level: 3 }
                Repeater {
                    model: deviceModel
                    delegate: Loader {
                        active: !model.isPaired
                        Layout.fillWidth: true
                        sourceComponent: active ? deviceCardComponent : null
                        onLoaded: { item.deviceData = Qt.binding(function() { return model }) }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    opacity: 0.6
                    visible: {
                        for (var i = 0; i < deviceModel.count; i++) if (!deviceModel.get(i).isPaired) return false
                        return true
                    }
                    text: "No unpaired devices nearby. Open KDE Connect on your phone and make sure it's on the same network."
                }

                Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }

                Kirigami.Heading { text: "Your Devices"; level: 3 }
                Repeater {
                    model: deviceModel
                    delegate: Loader {
                        active: model.isPaired
                        Layout.fillWidth: true
                        sourceComponent: active ? deviceCardComponent : null
                        onLoaded: { item.deviceData = Qt.binding(function() { return model }) }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    opacity: 0.6
                    visible: {
                        for (var i = 0; i < deviceModel.count; i++) if (deviceModel.get(i).isPaired) return false
                        return true
                    }
                    text: "No paired devices yet. Pair a nearby device above to get started."
                }
            }

            Kirigami.Separator { Layout.fillWidth: true; visible: kdeconnectInstalled && backendAvailable }

            // -- Troubleshooting ------------------------------------------------
            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.largeSpacing
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Can't find your phone?"; level: 4 }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "1. Make sure ReyOS and your phone are connected to the same network." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "2. Open KDE Connect on the phone." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "3. Make sure KDE Connect is running on ReyOS." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "4. Check the firewall." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "5. On a different network (VPN, hotspot)? Add its IP address below." }
                    RowLayout {
                        Controls.Button {
                            text: "Check Connection"
                            icon.name: "network-connect"
                            onClicked: backend.refreshDiagnostics()
                        }
                        Controls.Button {
                            text: "Allow in Firewall"
                            icon.name: "security-medium"
                            visible: diagnostics.firewallOpen === false
                            onClicked: confirmFirewall.open()
                        }
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        visible: diagnostics.daemonRunning !== undefined
                        text: {
                            var lines = []
                            lines.push("KDE Connect installed: " + (diagnostics.installed ? "yes" : "no"))
                            lines.push("Service running: " + (diagnostics.daemonRunning ? "yes" : "no"))
                            if (diagnostics.selfName) lines.push("This device is announced as: " + diagnostics.selfName)
                            if (diagnostics.firewallDetail) lines.push(diagnostics.firewallDetail)
                            return lines.join("\n")
                        }
                    }

                    Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }
                    Kirigami.Heading { text: "Connect by IP Address"; level: 5 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        opacity: 0.7
                        text: "KDE Connect normally finds devices by broadcasting on the local network. If your phone is reachable but on a different network segment, add its IP address here instead."
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Controls.TextField {
                            id: customIpField
                            Layout.fillWidth: true
                            placeholderText: "192.168.1.42"
                            onAccepted: { backend.addCustomDevice(text); text = "" }
                        }
                        Controls.Button {
                            text: "Add"
                            icon.name: "list-add"
                            onClicked: { backend.addCustomDevice(customIpField.text); customIpField.text = "" }
                        }
                    }
                    Repeater {
                        model: customDeviceModel
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { Layout.fillWidth: true; text: model.address }
                            Controls.Button {
                                text: "Remove"
                                icon.name: "edit-delete-remove"
                                onClicked: backend.removeCustomDevice(model.address)
                            }
                        }
                    }
                }
            }
        }
    }

    Controls.Dialog {
        id: confirmFirewall
        title: "Allow KDE Connect through the firewall?"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: backend.openFirewallForKdeConnect()
        Controls.Label {
            wrapMode: Text.Wrap
            text: "This opens ports 1714-1764 (TCP and UDP) — the range KDE Connect itself needs to discover and talk to your devices. No other ports are affected."
        }
    }

    Component {
        id: deviceCardComponent
        DeviceCard {
            onPairRequested: backend.requestPairing(deviceData.id)
            onAcceptRequested: backend.acceptPairing(deviceData.id)
            onRejectRequested: backend.rejectPairing(deviceData.id)
            onOpenRequested: pageStack.push(Qt.resolvedUrl("DeviceDetailPage.qml"), {deviceId: deviceData.id})
            onSendFileRequested: backend.openFilePickerAndSend(deviceData.id)
        }
    }
}
