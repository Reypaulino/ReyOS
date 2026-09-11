import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "VPN"

    property bool busy: false
    property string activeProfile: ""

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshVpnStatus()
    }

    Connections {
        target: backend
        function onVpnStatusReady(info) {
            busy = false
            activeProfile = info.active || ""
            profileModel.clear()
            for (var i = 0; i < info.profiles.length; i++) profileModel.append({ name: info.profiles[i] })
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
        function onVpnConfigSelected(path) {
            busy = false
            if (path.length > 0) { busy = true; backend.importVpnConfig(path) }
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: profileModel }

    Controls.Dialog {
        id: confirmRemove
        title: "Remove VPN profile"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingName: ""
        onAccepted: { busy = true; backend.deleteVpnConfig(pendingName) }
        Controls.Label {
            text: "Remove the \"" + confirmRemove.pendingName + "\" VPN profile? This disconnects it first if active."
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
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Status"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label {
                        text: activeProfile.length > 0 ? ("Connected: " + activeProfile) : "Not connected"
                        color: activeProfile.length > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "Bring your own WireGuard config (.conf) from any VPN provider — nothing is bundled with ReyOS."
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Import config"; level: 3 }
                Controls.Button {
                    text: "Browse & import…"
                    enabled: !busy
                    onClicked: { busy = true; backend.pickVpnConfigFile() }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Profiles"; level: 3 }
                Repeater {
                    model: profileModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label {
                            text: name
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            font.bold: name === activeProfile
                        }
                        Controls.Label {
                            visible: name === activeProfile
                            text: "Connected"
                            color: Kirigami.Theme.positiveTextColor
                        }
                        Controls.Button {
                            text: "Connect"
                            enabled: !busy && name !== activeProfile
                            onClicked: { busy = true; backend.connectVpn(name) }
                        }
                        Controls.Button {
                            text: "Disconnect"
                            enabled: !busy && name === activeProfile
                            onClicked: { busy = true; backend.disconnectVpn(name) }
                        }
                        Controls.Button {
                            text: "Remove"
                            enabled: !busy
                            onClicked: { confirmRemove.pendingName = name; confirmRemove.open() }
                        }
                    }
                }
                Controls.Label {
                    visible: profileModel.count === 0 && !busy
                    text: "No VPN profiles imported yet."
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
