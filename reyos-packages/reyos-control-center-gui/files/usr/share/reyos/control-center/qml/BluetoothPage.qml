import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Bluetooth"

    property bool busy: false
    property bool hasAdapter: false
    property bool powered: false
    property bool scanning: false
    // Separate from `busy`: the live scan refresh clears `busy` every 2 s,
    // and re-enabling the buttons mid-pair let a second click start another
    // action on top of the running one (QThread abort, app crash).
    property bool acting: false
    // Start looking for devices as soon as the page is open with Bluetooth
    // on (or once it is turned on here) -- nobody should have to find the
    // Scan button just to see their device.
    property bool autoScanned: false

    actions: [
        Kirigami.Action {
            text: scanning ? "Scanning..." : "Scan"
            icon.name: "view-refresh"
            enabled: hasAdapter && powered && !busy && !scanning && !acting
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
            scanning = info.scanning
            if (powered && !autoScanned && !scanning) {
                autoScanned = true
                backend.scanBluetoothDevices()
            }
            if (!powered) autoScanned = false
            deviceModel.clear()
            for (var i = 0; i < info.devices.length; i++) deviceModel.append(info.devices[i])
        }
        function onActionFinished(ok, message) {
            acting = false
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
            refresh()
        }
    }

    Component.onCompleted: refresh()

    // Keeps "Paired" / "Connected" current without clicking anything, e.g.
    // a controller that connects itself a few seconds after pairing or is
    // switched on later. Skipped while scanning (that refreshes every 2 s).
    Timer {
        interval: 5000
        repeat: true
        running: hasAdapter && powered && !scanning && !acting
        onTriggered: backend.refreshBluetoothStatus()
    }
    Component.onDestruction: backend.stopBluetoothScan()

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
                    enabled: !busy && !acting
                    onClicked: { acting = true; backend.setBluetoothPowered(!powered) }
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
                Controls.Label {
                    visible: scanning
                    Layout.fillWidth: true
                    text: "Searching... Put your device in pairing mode now (on an Xbox controller, hold the small pair button on top until the logo flashes fast), then click Pair as soon as it appears."
                    wrapMode: Text.Wrap
                }
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
                            enabled: !busy && !acting
                            onClicked: { acting = true; statusLabel.text = ""; backend.pairBluetoothDevice(mac) }
                        }
                        Controls.Button {
                            text: connected ? "Disconnect" : "Connect"
                            visible: paired
                            enabled: !busy && !acting
                            onClicked: {
                                acting = true
                                if (connected) backend.disconnectBluetoothDevice(mac)
                                else backend.connectBluetoothDevice(mac)
                            }
                        }
                        Controls.Button {
                            text: "Remove"
                            visible: paired
                            enabled: !busy && !acting
                            onClicked: { acting = true; backend.removeBluetoothDevice(mac) }
                        }
                    }
                }
                Controls.Label {
                    visible: deviceModel.count === 0 && !busy && !scanning
                    text: "No devices found -- put your device in pairing mode, then click Scan (top right) to search again."
                    wrapMode: Text.Wrap
                    opacity: 0.7
                }
            }
        }

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy || scanning || acting
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
