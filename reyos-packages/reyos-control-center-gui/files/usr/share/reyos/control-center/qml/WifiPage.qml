import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Wi-Fi"

    property bool busy: false
    property bool hasDevice: false
    // Named wifiEnabled, not "enabled" -- see the identical shadowing bug
    // (and fix) already documented in FirewallPage.qml's fwEnabled.
    property bool wifiEnabled: false

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            enabled: !busy
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshWifiStatus()
    }

    Connections {
        target: backend
        function onWifiStatusReady(info) {
            busy = false
            hasDevice = info.hasDevice
            wifiEnabled = info.enabled
            apModel.clear()
            for (var i = 0; i < info.aps.length; i++) apModel.append(info.aps[i])
            savedModel.clear()
            for (var j = 0; j < info.saved.length; j++) savedModel.append({ name: info.saved[j] })
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: apModel }
    ListModel { id: savedModel }

    Controls.Dialog {
        id: connectDialog
        title: "Connect to Wi-Fi"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        property string pendingSsid: ""
        property bool pendingSecured: true

        onOpened: pwField.text = ""

        footer: Controls.DialogButtonBox {
            Controls.Button {
                text: "Connect"
                enabled: !connectDialog.pendingSecured || pwField.text.length > 0
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.AcceptRole
                onClicked: {
                    busy = true
                    backend.connectWifi(connectDialog.pendingSsid, pwField.text)
                    connectDialog.close()
                }
            }
            Controls.Button {
                text: "Cancel"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.RejectRole
                onClicked: connectDialog.close()
            }
        }

        ColumnLayout {
            Controls.Label { text: "Network: " + connectDialog.pendingSsid; font.bold: true }
            Controls.TextField {
                id: pwField
                Layout.fillWidth: true
                visible: connectDialog.pendingSecured
                placeholderText: "Password"
                echoMode: TextInput.Password
            }
        }
    }

    Controls.Dialog {
        id: confirmForget
        title: "Forget network"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingName: ""
        onAccepted: { busy = true; backend.forgetWifi(pendingName) }
        Controls.Label {
            text: "Forget saved network \"" + confirmForget.pendingName + "\"?"
            wrapMode: Text.Wrap
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: !hasDevice && !busy
            contentItem: Controls.Label {
                text: "No Wi-Fi hardware found."
                opacity: 0.7
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: hasDevice
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Wi-Fi"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label {
                        text: wifiEnabled ? "On" : "Off"
                        color: wifiEnabled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                    }
                }
                Controls.Button {
                    text: wifiEnabled ? "Turn off" : "Turn on"
                    enabled: !busy
                    onClicked: { busy = true; backend.setWifiRadioEnabled(!wifiEnabled) }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: hasDevice && wifiEnabled
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Available networks"; level: 3 }
                Repeater {
                    model: apModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Label { text: ssid; font.bold: inUse; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.Label { text: signal + "%"; opacity: 0.7 }
                        Controls.Label { visible: inUse; text: "connected"; color: Kirigami.Theme.positiveTextColor }
                        Controls.Button {
                            text: "Connect"
                            visible: !inUse
                            enabled: !busy
                            onClicked: {
                                connectDialog.pendingSsid = ssid
                                connectDialog.pendingSecured = security.length > 0 && security !== "--"
                                connectDialog.open()
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: apModel.count === 0 && !busy
                    text: "No networks found."
                    opacity: 0.7
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: hasDevice && savedModel.count > 0
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Saved networks"; level: 3 }
                Repeater {
                    model: savedModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label { text: name; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.Button {
                            text: "Forget"
                            enabled: !busy
                            onClicked: { confirmForget.pendingName = name; confirmForget.open() }
                        }
                    }
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
