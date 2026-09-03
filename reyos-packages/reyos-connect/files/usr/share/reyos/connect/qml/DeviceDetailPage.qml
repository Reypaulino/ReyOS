import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    property string deviceId: ""
    property var device: ({})
    property var remoteCommands: []
    property var remoteDesktop: ({available: false, backendId: "", backend: "", enabled: false, active: false})
    property var sshInfo: ({installed: false, enabled: false, active: false})
    property var linkedBluetooth: ({})

    title: device.name || "Device"

    function reload() {
        device = backend.deviceDetail(deviceId)
        remoteCommands = device.canRunCommand ? backend.listRemoteCommands(deviceId) : []
        remoteDesktop = backend.remoteDesktopStatus()
        sshInfo = backend.sshStatus()
        linkedBluetooth = backend.linkedBluetoothInfo(deviceId)
    }

    Component.onCompleted: reload()

    Connections {
        target: backend
        function onDevicesChanged() { reload() }
        function onActionFinished(ok, message) { reload() }
    }

    Controls.Dialog {
        id: sshInstructionsDialog
        title: "SSH Terminal Instructions"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Close
        property var info: ({user: "", hostname: "", addresses: []})
        width: Math.min(440, parent ? parent.width - 40 : 440)

        ColumnLayout {
            width: parent.width
            spacing: Kirigami.Units.smallSpacing
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: "From another device on the same network or VPN, connect with:"
            }
            Repeater {
                model: sshInstructionsDialog.info.addresses
                delegate: Controls.TextField {
                    Layout.fillWidth: true
                    readOnly: true
                    selectByMouse: true
                    text: "ssh " + sshInstructionsDialog.info.user + "@" + modelData
                }
            }
            Controls.Label {
                visible: sshInstructionsDialog.info.addresses.length === 0
                opacity: 0.7
                wrapMode: Text.Wrap
                text: "No network address found yet -- connect to Wi-Fi/VPN first."
            }
        }
    }

    Controls.Dialog {
        id: linkDialog
        title: "Link Bluetooth Device"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Close
        property var candidates: []
        width: Math.min(400, parent ? parent.width - 40 : 400)

        ColumnLayout {
            width: parent.width
            Repeater {
                model: linkDialog.candidates
                delegate: Controls.ItemDelegate {
                    Layout.fillWidth: true
                    text: modelData.name + " (" + modelData.shortId + ")"
                    onClicked: {
                        backend.linkBluetoothDevice(deviceId, modelData.mac)
                        linkDialog.close()
                        reload()
                    }
                }
            }
            Controls.Label {
                visible: linkDialog.candidates.length === 0
                opacity: 0.6
                text: "No paired Bluetooth devices found."
            }
        }
    }

    actions: [
        Kirigami.Action {
            text: "Close"
            icon.name: "window-close"
            onTriggered: applicationWindow().pageStack.pop()
        },
        Kirigami.Action {
            text: "Menu"
            icon.name: "application-menu"
            onTriggered: applicationWindow().globalDrawer.open()
        },
        Kirigami.Action {
            text: "Unpair"
            icon.name: "edit-delete-remove"
            visible: device.isPaired
            onTriggered: confirmUnpair.open()
        }
    ]

    Controls.Dialog {
        id: confirmUnpair
        title: "Unpair " + (device.name || "this device") + "?"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: { backend.unpairDevice(deviceId); applicationWindow().pageStack.pop() }
        Controls.Label { text: "You'll need to pair again to reconnect." }
    }

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon {
                        source: device.statusIconName || "smartphone"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.huge
                        Layout.preferredHeight: Kirigami.Units.iconSizes.huge
                    }
                    ColumnLayout {
                        spacing: 2
                        Kirigami.Heading { level: 2; text: device.name || "" }
                        Controls.Label { opacity: 0.7; text: "Type: " + (device.type || "unknown") }
                        Controls.Label { opacity: 0.7; visible: !!device.ipAddress; text: "IP Address: " + (device.ipAddress || "") }
                        Controls.Label {
                            text: {
                                switch (device.state) {
                                    case "available": return "Available"
                                    case "pairingOutgoing": return "Pairing…"
                                    case "pairingIncoming": return "Wants to pair"
                                    case "connected": return "Connected"
                                    case "disconnected": return "Paired · Disconnected"
                                    case "unreachable": return "Unreachable"
                                    default: return device.state || ""
                                }
                            }
                        }
                        Controls.Label {
                            visible: !!(device.battery)
                            text: device.battery ? ("Battery: " + device.battery.charge + "% · " + (device.battery.isCharging ? "Charging" : "Not Charging")) : ""
                        }
                        Controls.Label {
                            visible: !device.battery
                            opacity: 0.6
                            text: "Battery information unavailable"
                        }
                    }
                }

                RowLayout {
                    visible: device.state === "available"
                    Controls.Button { text: "Pair"; highlighted: true; onClicked: backend.requestPairing(deviceId) }
                }
                RowLayout {
                    visible: device.state === "pairingIncoming"
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Button { text: "Accept"; highlighted: true; onClicked: backend.acceptPairing(deviceId) }
                    Controls.Button { text: "Reject"; onClicked: backend.rejectPairing(deviceId) }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: device.isPaired
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Heading { text: "Quick Actions"; level: 4 }

                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Button {
                        visible: device.canShare && device.state === "connected"
                        text: "Send File"
                        icon.name: "document-send"
                        onClicked: backend.openFilePickerAndSend(deviceId)
                    }
                    Controls.Button {
                        visible: device.canFindMyPhone && device.state === "connected"
                        text: "Find Phone"
                        icon.name: "audio-volume-high"
                        onClicked: backend.ringDevice(deviceId)
                    }
                    Controls.Button {
                        visible: device.canPing && device.state === "connected"
                        text: "Ping"
                        icon.name: "network-connect"
                        onClicked: backend.pingDevice(deviceId)
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true; visible: device.canShare }
                ColumnLayout {
                    visible: device.canShare
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Send Link"; level: 5 }
                    RowLayout {
                        Layout.fillWidth: true
                        Controls.TextField {
                            id: linkField
                            Layout.fillWidth: true
                            placeholderText: "https://example.com"
                        }
                        Controls.Button {
                            text: "Send to " + (device.name || "device")
                            enabled: device.state === "connected"
                            onClicked: { backend.sendUrlToDevice(deviceId, linkField.text); linkField.text = "" }
                        }
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true; visible: device.canClipboard }
                ColumnLayout {
                    visible: device.canClipboard
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Clipboard Sharing"; level: 5 }
                    Controls.Label { text: device.clipboardAutoDisabled ? "Automatic sharing is off" : "Available" }
                    Controls.Button {
                        text: "Send Clipboard to Device"
                        enabled: device.state === "connected"
                        onClicked: backend.sendClipboardToDevice(deviceId)
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true; visible: device.canRemoteKeyboard }
                ColumnLayout {
                    visible: device.canRemoteKeyboard
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Remote Input"; level: 5 }
                    Controls.Label {
                        wrapMode: Text.WordWrap
                        text: device.remoteKeyboardActive
                            ? "Your phone currently has its remote-input view open and is controlling this desktop."
                            : "Open the trackpad/keyboard view in KDE Connect on your phone to control this desktop."
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true; visible: device.canRunCommand }
                ColumnLayout {
                    visible: device.canRunCommand
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Remote Commands"; level: 5 }
                    Controls.Label {
                        wrapMode: Text.WordWrap
                        text: "Turn on the fixed, ReyOS-safe commands you want available from your phone's Run Commands menu. There's no free-text command field -- only this fixed list."
                    }
                    Repeater {
                        model: remoteCommands
                        delegate: Controls.CheckBox {
                            text: modelData.name
                            checked: modelData.enabled
                            onToggled: backend.setRemoteCommandEnabled(deviceId, modelData.id, checked)
                        }
                    }
                    Controls.Button {
                        text: "Advanced (KDE Connect app)…"
                        icon.name: "configure"
                        onClicked: backend.openRemoteCommandsConfig(deviceId)
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: device.isPaired
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Remote Desktop"; level: 4 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: !remoteDesktop.available
                        ? "Remote Desktop backend unavailable."
                        : remoteDesktop.active
                            ? ("Active (" + remoteDesktop.backend + ") -- listening on LAN/VPN only.")
                            : remoteDesktop.enabled
                                ? ("Enabled but not currently running (" + remoteDesktop.backend + ").")
                                : ("Available, disabled by default (" + remoteDesktop.backend + ") -- set a username/password first.")
                    color: remoteDesktop.active ? Kirigami.Theme.positiveTextColor
                        : remoteDesktop.available ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.disabledTextColor
                }
                RowLayout {
                    visible: remoteDesktop.available
                    Layout.fillWidth: true
                    Controls.Button {
                        text: "Remote Desktop Settings"
                        onClicked: backend.openRemoteDesktopSettings()
                    }
                    Controls.Button {
                        text: remoteDesktop.active ? "Stop Session" : "Start Session"
                        onClicked: remoteDesktop.active ? backend.stopRemoteDesktop() : backend.startRemoteDesktop()
                    }
                }
                Controls.Label {
                    visible: remoteDesktop.available
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.6
                    font.pointSize: 8
                    text: "Username/password are set through KDE's own Remote Desktop settings (KWallet-backed) -- ReyOS Connect never stores a password itself. Disabled by default; only reachable over LAN/VPN, never exposed publicly."
                }

                Kirigami.Separator { Layout.fillWidth: true }

                Kirigami.Heading { text: "SSH Remote Terminal"; level: 4 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: sshInfo.active ? "Enabled -- listening on VPN/LAN." : (sshInfo.enabled ? "Enabled but not currently running." : "Disabled")
                    color: sshInfo.active ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                }
                Controls.Button {
                    text: "Open Terminal Instructions"
                    icon.name: "utilities-terminal"
                    visible: sshInfo.active
                    onClicked: {
                        sshInstructionsDialog.info = backend.sshConnectionInfo()
                        sshInstructionsDialog.open()
                    }
                }
                Controls.Button {
                    text: "Configure…"
                    icon.name: "configure"
                    visible: !sshInfo.active
                    onClicked: backend.openControlCenter()
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: device.isPaired
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Bluetooth"; level: 4 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    visible: !linkedBluetooth.mac
                    opacity: 0.7
                    text: "Not linked to a Bluetooth device yet. Link it once this phone is actually Bluetooth-paired to merge its phone capabilities here."
                }
                RowLayout {
                    visible: !!linkedBluetooth.mac
                    Controls.Label {
                        text: linkedBluetooth.found
                            ? (linkedBluetooth.name + " · " + (linkedBluetooth.connected ? "Connected" : "Paired"))
                            : "Linked device no longer paired."
                    }
                    Item { Layout.fillWidth: true }
                    Controls.Button {
                        text: "Unlink"
                        onClicked: { backend.unlinkBluetoothDevice(deviceId); reload() }
                    }
                }
                Controls.Button {
                    text: "Link Bluetooth Device…"
                    icon.name: "preferences-system-bluetooth"
                    onClicked: { linkDialog.candidates = backend.listBluetoothDevicesSync(); linkDialog.open() }
                }
            }
        }

        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.gridUnit * 2
            visible: device.isPaired && device.loadedPlugins && device.loadedPlugins.length === 0 && device.state !== "connected"
            icon.name: "network-disconnect"
            text: "This device is not connected right now"
            explanation: "Capabilities will appear here once it's reachable again."
        }
    }
}
