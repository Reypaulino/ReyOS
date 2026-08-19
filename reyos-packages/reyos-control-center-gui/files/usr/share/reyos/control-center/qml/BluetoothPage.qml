import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Bluetooth"

    property bool busy: false
    property bool hasAdapter: false
    property bool powered: false

    actions: [
        Kirigami.Action {
            text: "Scan"
            icon.name: "view-refresh"
            enabled: hasAdapter && powered && !busy
            onTriggered: { busy = true; backend.scanBluetoothDevices() }
        }
    ]

    function refresh() {
        busy = true
        backend.refreshBluetoothStatus()
    }

    Connections {
        target: backend
        function onBluetoothStatusReady(info) {
            busy = false
            hasAdapter = info.hasAdapter
            powered = info.powered
            deviceModel.clear()
            for (var i = 0; i < info.devices.length; i++) deviceModel.append(info.devices[i])
        }
        function onActionFinished(ok, message) {
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: deviceModel }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: !hasAdapter && !busy
            contentItem: Controls.Label {
                text: "No Bluetooth adapter found."
                opacity: 0.7
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: hasAdapter
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Bluetooth"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label {
                        text: powered ? "On" : "Off"
                        color: powered ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                    }
                }
                Controls.Button {
                    text: powered ? "Turn off" : "Turn on"
                    enabled: !busy
                    onClicked: { busy = true; backend.setBluetoothPowered(!powered) }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: hasAdapter && powered
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Devices"; level: 3 }
                Repeater {
                    model: deviceModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        ColumnLayout {
                            spacing: 0
                            Layout.fillWidth: true
                            Controls.Label { text: name; font.bold: true }
                            Controls.Label {
                                text: connected ? "Connected" : (paired ? "Paired" : "Not paired")
                                color: connected ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                                font.pointSize: 9
                            }
                        }
                        Controls.Button {
                            text: "Pair"
                            visible: !paired
                            enabled: !busy
                            onClicked: { busy = true; backend.pairBluetoothDevice(mac) }
                        }
                        Controls.Button {
                            text: connected ? "Disconnect" : "Connect"
                            visible: paired
                            enabled: !busy
                            onClicked: {
                                busy = true
                                if (connected) backend.disconnectBluetoothDevice(mac)
                                else backend.connectBluetoothDevice(mac)
                            }
                        }
                        Controls.Button {
                            text: "Remove"
                            visible: paired
                            enabled: !busy
                            onClicked: { busy = true; backend.removeBluetoothDevice(mac) }
                        }
                    }
                }
                Controls.Label {
                    visible: deviceModel.count === 0 && !busy
                    text: "No devices yet -- click Scan (top right) to look for nearby devices."
                    wrapMode: Text.Wrap
                    opacity: 0.7
                }
            }
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
