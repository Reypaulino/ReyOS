import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Remote Access"

    property var vpnInfo: ({backends: {}, tailscale: {}, wireguard: {}})
    property string selectedBackend: "tailscale"
    property var testResult: null
    property var testChecks: []
    property bool testReady: false
    property bool testRun: false
    property bool busy: false

    function refresh() { busy = true; backend.refreshVpnStatus() }

    Component.onCompleted: refresh()

    Connections {
        target: backend
        function onVpnStatusReady(info) {
            busy = false
            vpnInfo = info
            if (info.backends) {
                if (selectedBackend === "tailscale" && !info.backends.tailscale && info.backends.wireguard)
                    selectedBackend = "wireguard"
                else if (selectedBackend === "wireguard" && !info.backends.wireguard && info.backends.tailscale)
                    selectedBackend = "tailscale"
            }
        }
        function onRemoteConnectionTestReady(result) {
            busy = false
            testResult = result
            testChecks = (result && result.checks) ? result.checks : []
            testReady = !!(result && result.ready)
            testRun = true
        }
        function onActionFinished(ok, message) { busy = false; statusLabel.text = message; refresh() }
    }

    actions: [
        Kirigami.Action { text: "Close"; icon.name: "window-close"; onTriggered: applicationWindow().pageStack.pop() },
        Kirigami.Action { text: "Menu"; icon.name: "application-menu"; onTriggered: applicationWindow().globalDrawer.open() },
        Kirigami.Action { text: "Refresh"; icon.name: "view-refresh"; onTriggered: refresh() }
    ]

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: !vpnInfo.backends || (!vpnInfo.backends.tailscale && !vpnInfo.backends.wireguard)
            type: Kirigami.MessageType.Information
            text: "No VPN backend found. Install Tailscale or set up WireGuard (via Control Center) to reach this device when you're away from home."
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: vpnInfo.backends && (vpnInfo.backends.tailscale || vpnInfo.backends.wireguard)
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Heading { text: "VPN Provider"; level: 3 }
                RowLayout {
                    Controls.RadioButton {
                        text: "Tailscale"
                        visible: vpnInfo.backends && vpnInfo.backends.tailscale
                        checked: selectedBackend === "tailscale"
                        onToggled: if (checked) selectedBackend = "tailscale"
                    }
                    Controls.RadioButton {
                        text: "WireGuard"
                        visible: vpnInfo.backends && vpnInfo.backends.wireguard
                        checked: selectedBackend === "wireguard"
                        onToggled: if (checked) selectedBackend = "wireguard"
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true }

                // -- Tailscale status --
                ColumnLayout {
                    visible: selectedBackend === "tailscale" && vpnInfo.tailscale
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    RowLayout {
                        Kirigami.Heading { text: "Status"; level: 4 }
                        Item { Layout.fillWidth: true }
                        Controls.Label {
                            text: vpnInfo.tailscale && vpnInfo.tailscale.connected ? "Connected" : "Not connected"
                            color: vpnInfo.tailscale && vpnInfo.tailscale.connected ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                            font.bold: true
                        }
                    }
                    Controls.Label {
                        visible: vpnInfo.tailscale && !!vpnInfo.tailscale.selfIp
                        text: "ReyOS Address: " + (vpnInfo.tailscale ? vpnInfo.tailscale.selfIp : "")
                    }
                    Controls.Label {
                        visible: vpnInfo.tailscale && !vpnInfo.tailscale.authenticated
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Not logged in yet. Authenticate once from a terminal (tailscale up) -- ReyOS Connect never starts a login flow for you."
                    }
                    RowLayout {
                        visible: vpnInfo.tailscale && vpnInfo.tailscale.authenticated
                        Controls.Button {
                            text: vpnInfo.tailscale && vpnInfo.tailscale.connected ? "Disconnect" : "Connect"
                            enabled: !busy
                            onClicked: { busy = true; backend.setTailscaleConnected(!(vpnInfo.tailscale && vpnInfo.tailscale.connected)) }
                        }
                    }
                    Repeater {
                        model: vpnInfo.tailscale ? vpnInfo.tailscale.peers : []
                        delegate: Controls.Label {
                            opacity: 0.7
                            text: modelData.name + ": " + (modelData.online ? "online" : "offline") + (modelData.ip ? " (" + modelData.ip + ")" : "")
                        }
                    }
                }

                // -- WireGuard status --
                ColumnLayout {
                    visible: selectedBackend === "wireguard" && vpnInfo.wireguard
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Interfaces"; level: 4 }
                    Controls.Label {
                        visible: vpnInfo.wireguard && !vpnInfo.wireguard.profilesReadable
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Some profiles may not be listed -- /etc/wireguard needs elevated access to fully enumerate. Manage profiles from Control Center."
                    }
                    Repeater {
                        model: vpnInfo.wireguard ? vpnInfo.wireguard.interfaces : []
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { Layout.fillWidth: true; text: modelData.name + (modelData.active ? " (active)" : "") }
                            Controls.Button {
                                text: modelData.active ? "Disconnect" : "Connect"
                                enabled: !busy
                                onClicked: {
                                    busy = true
                                    if (modelData.active) backend.disconnectWireguard(modelData.name, modelData.source)
                                    else backend.connectWireguard(modelData.name, modelData.source)
                                }
                            }
                        }
                    }
                    Controls.Label {
                        visible: !vpnInfo.wireguard || vpnInfo.wireguard.interfaces.length === 0
                        opacity: 0.6
                        text: "No WireGuard interfaces found."
                    }
                }

                Controls.Button {
                    text: "VPN Settings (Control Center)"
                    icon.name: "configure"
                    onClicked: backend.openControlCenter()
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: vpnInfo.backends && (vpnInfo.backends.tailscale || vpnInfo.backends.wireguard)
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Remote Connection Test"; level: 3 }
                Controls.Button {
                    text: "Test Remote Connection"
                    enabled: !busy
                    onClicked: { busy = true; testRun = false; testChecks = []; backend.testRemoteConnection(selectedBackend, "", true) }
                }
                Repeater {
                    model: testChecks
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { text: modelData.check; font.bold: true }
                            Item { Layout.fillWidth: true }
                            Controls.Label {
                                text: modelData.passed ? "PASS" : "FAIL"
                                color: modelData.passed ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                                font.bold: true
                            }
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.smallSpacing
                            wrapMode: Text.Wrap
                            opacity: 0.7
                            font.pointSize: 9
                            text: modelData.detail
                        }
                        Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }
                    }
                }
                Controls.Label {
                    visible: testRun
                    font.bold: true
                    color: testReady ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
                    text: testReady ? "Remote access ready." : "Not ready yet -- see checks above."
                }
            }
        }

        Controls.ProgressBar { Layout.fillWidth: true; indeterminate: true; visible: busy }
        Controls.Label { id: statusLabel; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
