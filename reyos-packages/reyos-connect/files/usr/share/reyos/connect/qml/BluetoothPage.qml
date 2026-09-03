import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Bluetooth"

    property var adapter: ({available: false, hasAdapter: false, powered: false})
    property var devices: []
    property bool busy: false
    property var probeResults: ({})   // mac -> {contacts, messages, calls}
    property var probingMac: ""

    function refresh() { busy = true; backend.refreshBluetoothStatus() }

    Component.onCompleted: refresh()

    Connections {
        target: backend
        function onBluetoothStatusReady(info) {
            busy = false
            adapter = info.adapter || {available: false, hasAdapter: false, powered: false}
            devices = info.devices || []
        }
        function onActionFinished(ok, message) { statusLabel.text = message }
        function onPhoneCapabilitiesReady(mac, result) {
            probingMac = ""
            var updated = Object.assign({}, probeResults)
            updated[mac] = result
            probeResults = updated
        }
    }

    actions: [
        Kirigami.Action { text: "Close"; icon.name: "window-close"; onTriggered: applicationWindow().pageStack.pop() },
        Kirigami.Action { text: "Menu"; icon.name: "application-menu"; onTriggered: applicationWindow().globalDrawer.open() },
        Kirigami.Action { text: "Refresh"; icon.name: "view-refresh"; onTriggered: refresh() }
    ]

    function capLabel(state) {
        if (state === "AVAILABLE") return "Advertised"
        if (state === "UNAVAILABLE") return "Unavailable"
        return "Not tested"
    }

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        Controls.ProgressBar { Layout.fillWidth: true; indeterminate: true; visible: busy }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: !busy && !adapter.available
            contentItem: RowLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: "preferences-system-bluetooth"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.large
                    Layout.preferredHeight: Kirigami.Units.iconSizes.large
                }
                ColumnLayout {
                    spacing: 2
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Bluetooth isn't available"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "No Bluetooth service (org.bluez) was found on this device."
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: !busy && adapter.available && !adapter.hasAdapter
            contentItem: RowLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: "preferences-system-bluetooth"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.large
                    Layout.preferredHeight: Kirigami.Units.iconSizes.large
                }
                Kirigami.Heading { text: "No Bluetooth adapter found"; level: 4 }
            }
        }

        Repeater {
            model: devices
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        Kirigami.Icon {
                            source: modelData.icon || "bluetooth-active"
                            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                            Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                        }
                        ColumnLayout {
                            spacing: 0
                            Layout.fillWidth: true
                            Controls.Label { text: modelData.name; font.bold: true }
                            Controls.Label {
                                opacity: 0.6
                                font.pointSize: 9
                                text: modelData.shortId + " · " + (modelData.connected ? "Connected" : "Paired")
                            }
                        }
                        Controls.Button {
                            text: modelData.connected ? "Disconnect" : "Connect"
                            enabled: !busy
                            onClicked: {
                                busy = true
                                if (modelData.connected) backend.disconnectBluetoothDevice(modelData.mac)
                                else backend.connectBluetoothDevice(modelData.mac)
                            }
                        }
                    }
                    RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Label { text: "Contacts: " + capLabel(modelData.capabilities.contacts); opacity: 0.7; font.pointSize: 9 }
                        Controls.Label { text: "Calls: " + capLabel(modelData.capabilities.calls); opacity: 0.7; font.pointSize: 9 }
                        Controls.Label { text: "Messages: " + capLabel(modelData.capabilities.messages); opacity: 0.7; font.pointSize: 9 }
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.6
                        font.pointSize: 9
                        text: "\"Advertised\" means this device reports supporting that profile -- it stays untested until actually used with a real phone."
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Controls.Button {
                            text: probingMac === modelData.mac ? "Testing…" : "Test Phone Capabilities"
                            enabled: probingMac === ""
                            onClicked: { probingMac = modelData.mac; backend.probePhoneCapabilities(modelData.mac) }
                        }
                    }
                    ColumnLayout {
                        visible: !!probeResults[modelData.mac]
                        Layout.fillWidth: true
                        spacing: 2
                        Repeater {
                            model: probeResults[modelData.mac] ? [
                                {label: "Contacts", r: probeResults[modelData.mac].contacts},
                                {label: "Calls", r: probeResults[modelData.mac].calls},
                                {label: "Messages", r: probeResults[modelData.mac].messages},
                            ] : []
                            delegate: ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Controls.Label {
                                    font.pointSize: 9
                                    font.bold: true
                                    color: modelData.r.result === "AVAILABLE" ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
                                    text: modelData.label + ": " + modelData.r.result
                                }
                                Controls.Label {
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    opacity: 0.7
                                    font.pointSize: 8
                                    text: modelData.r.detail
                                }
                            }
                        }
                    }
                }
            }
        }

        Controls.Label {
            visible: !busy && adapter.hasAdapter && devices.length === 0
            opacity: 0.6
            text: "No paired Bluetooth devices."
        }

        Controls.Label { id: statusLabel; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
