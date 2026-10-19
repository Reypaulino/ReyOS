import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    property string deviceId: ""
    property var device: ({})
    property var remoteCommands: []
    property var linkedBluetooth: ({})
    readonly property bool connected: device.state === "connected"

    title: device.name || "Device"

    function reload() {
        device = backend.deviceDetail(deviceId)
        remoteCommands = device.canRunCommand ? backend.listRemoteCommands(deviceId) : []
        linkedBluetooth = backend.linkedBluetoothInfo(deviceId)
    }

    Component.onCompleted: reload()

    Connections {
        target: backend
        function onDevicesChanged() { page.reload() }
    }

    actions: [
        Kirigami.Action {
            text: "Unpair"
            icon.name: "edit-delete-remove"
            visible: !!page.device.isPaired
            onTriggered: confirmUnpair.open()
        }
    ]

    Controls.Dialog {
        id: confirmUnpair
        title: "Unpair " + (page.device.name || "this device") + "?"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: { backend.unpairDevice(page.deviceId); applicationWindow().pageStack.pop() }
        Controls.Label { text: "You'll need to pair again to reconnect." }
    }

    Controls.Dialog {
        id: linkDialog
        title: "Link Bluetooth Device"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Close
        property var candidates: []
        width: Math.min(Kirigami.Units.gridUnit * 22, page.width - Kirigami.Units.gridUnit * 2)

        ColumnLayout {
            width: parent.width
            Repeater {
                model: linkDialog.candidates
                delegate: Controls.ItemDelegate {
                    Layout.fillWidth: true
                    text: modelData.name + " (" + modelData.shortId + ")"
                    onClicked: {
                        backend.linkBluetoothDevice(page.deviceId, modelData.mac)
                        linkDialog.close()
                        page.reload()
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

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        // -- Who / status ----------------------------------------------------------
        SectionCard {
            accented: page.connected
            contentItem: RowLayout {
                spacing: Kirigami.Units.gridUnit
                DeviceAvatar {
                    iconName: page.device.statusIconName || "smartphone"
                    size: Kirigami.Units.iconSizes.enormous
                    active: page.connected
                    Layout.alignment: Qt.AlignTop
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { level: 1; text: page.device.name || ""; Layout.fillWidth: true; elide: Text.ElideRight }
                    RowLayout {
                        spacing: Kirigami.Units.smallSpacing
                        StatusPill {
                            text: page.connected ? "Connected"
                                : page.device.state === "available" ? "Not paired"
                                : page.device.state === "pairingIncoming" ? "Wants to pair"
                                : page.device.state === "pairingOutgoing" ? "Pairing…"
                                : "Not reachable"
                            tone: page.connected ? "positive" : page.device.state === "pairingIncoming" ? "accent" : "muted"
                        }
                        Controls.Label {
                            opacity: 0.6
                            text: [page.device.type ? page.device.type.charAt(0).toUpperCase() + page.device.type.slice(1) : "", page.device.ipAddress || ""].filter(function(s) { return s }).join(" · ")
                        }
                    }
                    RowLayout {
                        visible: !!page.device.battery
                        spacing: Kirigami.Units.smallSpacing
                        Kirigami.Icon {
                            source: page.device.battery && page.device.battery.isCharging ? "battery-charging" : "battery"
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                        }
                        ReyOSProgressBar {
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 8
                            value: page.device.battery ? page.device.battery.charge / 100 : 0
                        }
                        Controls.Label {
                            text: page.device.battery ? (page.device.battery.charge + "% · " + (page.device.battery.isCharging ? "Charging" : "Not charging")) : ""
                            opacity: 0.75
                        }
                    }
                    Controls.Label {
                        visible: !!page.device.isPaired && !page.connected
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Not reachable right now. Open KDE Connect on it and join the same network or VPN; its actions appear here once it's back."
                    }
                    RowLayout {
                        visible: page.device.state === "available"
                        Controls.Button { text: "Pair"; highlighted: true; onClicked: backend.requestPairing(page.deviceId) }
                    }
                    RowLayout {
                        visible: page.device.state === "pairingIncoming"
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Button { text: "Accept"; highlighted: true; onClicked: backend.acceptPairing(page.deviceId) }
                        Controls.Button { text: "Reject"; onClicked: backend.rejectPairing(page.deviceId) }
                    }
                }
            }
        }

        // -- Actions -----------------------------------------------------------------
        SectionCard {
            visible: !!page.device.isPaired && page.connected && (!!page.device.canShare || !!page.device.canFindMyPhone || !!page.device.canPing || !!page.device.canClipboard)
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Quick actions"; level: 3 }
                Flow {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Button { visible: !!page.device.canShare; text: "Send file"; icon.name: "document-send"; onClicked: backend.openFilePickerAndSend(page.deviceId) }
                    Controls.Button { visible: !!page.device.canClipboard; text: "Send clipboard"; icon.name: "edit-paste"; onClicked: backend.sendClipboardToDevice(page.deviceId) }
                    Controls.Button { visible: !!page.device.canFindMyPhone; text: "Find phone"; icon.name: "audio-volume-high"; onClicked: backend.ringDevice(page.deviceId) }
                    Controls.Button { visible: !!page.device.canPing; text: "Ping"; icon.name: "network-connect"; onClicked: backend.pingDevice(page.deviceId) }
                }

                ColumnLayout {
                    visible: !!page.device.canShare
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Separator { Layout.fillWidth: true }
                    Kirigami.Heading { text: "Send a link"; level: 4 }
                    RowLayout {
                        Layout.fillWidth: true
                        Controls.TextField {
                            id: linkField
                            Layout.fillWidth: true
                            placeholderText: "https://example.com"
                            onAccepted: if (text.trim().length > 0) { backend.sendUrlToDevice(page.deviceId, text); text = "" }
                        }
                        Controls.Button {
                            text: "Send"
                            icon.name: "document-send"
                            enabled: linkField.text.trim().length > 0
                            onClicked: { backend.sendUrlToDevice(page.deviceId, linkField.text); linkField.text = "" }
                        }
                    }
                }

                Controls.Label {
                    visible: !!page.device.canClipboard
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.6
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    text: page.device.clipboardAutoDisabled ? "Automatic clipboard sharing is off; use Send clipboard." : "Clipboard is shared automatically."
                }
            }
        }

        // -- Phone as a remote ------------------------------------------------------------
        SectionCard {
            visible: !!page.device.isPaired && (!!page.device.canRemoteKeyboard || !!page.device.canRunCommand)
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Use it as a remote"; level: 3 }

                Controls.Label {
                    visible: !!page.device.canRemoteKeyboard
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: page.device.remoteKeyboardActive
                        ? "The phone's trackpad/keyboard view is open and controlling this desktop."
                        : "Open the trackpad/keyboard view in KDE Connect on the phone to control this desktop."
                }

                ColumnLayout {
                    visible: !!page.device.canRunCommand
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Separator { Layout.fillWidth: true; visible: !!page.device.canRemoteKeyboard }
                    Kirigami.Heading { text: "Commands the phone can run"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Pick from ReyOS's fixed, safe list. They show up in the phone's Run Commands menu. There's no free-text command."
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: page.width > Kirigami.Units.gridUnit * 30 ? 2 : 1
                        Repeater {
                            model: page.remoteCommands
                            delegate: Controls.CheckBox {
                                text: modelData.name
                                checked: modelData.enabled
                                onToggled: backend.setRemoteCommandEnabled(page.deviceId, modelData.id, checked)
                            }
                        }
                    }
                    Controls.Button {
                        text: "Advanced (KDE Connect app)…"
                        icon.name: "configure"
                        flat: true
                        onClicked: backend.openRemoteCommandsConfig(page.deviceId)
                    }
                }
            }
        }

        // -- Bluetooth link -------------------------------------------------------------
        SectionCard {
            visible: !!page.device.isPaired
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Bluetooth"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    visible: !page.linkedBluetooth.mac
                    opacity: 0.7
                    text: "Not linked to a Bluetooth device. Once this phone is also paired over Bluetooth, link it here to bring its phone features together."
                }
                RowLayout {
                    visible: !!page.linkedBluetooth.mac
                    Layout.fillWidth: true
                    Controls.Label {
                        Layout.fillWidth: true
                        text: page.linkedBluetooth.found
                            ? (page.linkedBluetooth.name + " · " + (page.linkedBluetooth.connected ? "Connected" : "Paired"))
                            : "Linked device is no longer paired."
                    }
                    Controls.Button { text: "Unlink"; onClicked: { backend.unlinkBluetoothDevice(page.deviceId); page.reload() } }
                }
                Controls.Button {
                    visible: !page.linkedBluetooth.mac
                    text: "Link Bluetooth device…"
                    icon.name: "network-bluetooth"
                    onClicked: { linkDialog.candidates = backend.listBluetoothDevicesSync(); linkDialog.open() }
                }
            }
        }

        Controls.Button {
            visible: !!page.device.isPaired
            flat: true
            icon.name: "computer"
            text: "Remote desktop and SSH for this computer →"
            onClicked: applicationWindow().openSection("remote-desktop")
        }
    }
}
