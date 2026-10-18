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
    property bool rdBusy: false
    property bool rdClient: false
    property var rdRecent: []
    property string rdMessage: ""
    property bool rdOk: false

    function refreshRemoteDesktop() {
        rdClient = backend.remoteDesktopClientAvailable()
        rdRecent = backend.recentRemoteDesktops()
    }

    function connectTo(protocol, host, port, user) {
        rdBusy = true
        rdMessage = ""
        backend.connectRemoteDesktop(protocol, host, port, user)
    }

    function refresh() { busy = true; backend.refreshVpnStatus() }

    Component.onCompleted: { refresh(); refreshRemoteDesktop() }

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
        function onRemoteDesktopConnectFinished(ok, message) {
            rdBusy = false
            rdOk = ok
            rdMessage = message
            refreshRemoteDesktop()
        }
    }

    actions: [
        Kirigami.Action { text: "Close"; icon.name: "window-close"; onTriggered: applicationWindow().pageStack.pop() },
        Kirigami.Action { text: "Menu"; icon.name: "application-menu"; onTriggered: applicationWindow().globalDrawer.open() },
        Kirigami.Action { text: "Refresh"; icon.name: "view-refresh"; onTriggered: { refresh(); refreshRemoteDesktop() } }
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

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Heading { text: "Connect to a Computer"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "See and control another computer's desktop: a Windows PC (RDP), another ReyOS or KDE computer with Remote Desktop turned on (RDP), or anything running a VNC server. Away from home, connect your VPN first."
                }
                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    visible: !rdClient
                    type: Kirigami.MessageType.Warning
                    text: "The remote desktop viewer (KRDC) isn't installed yet. Run Control Center → Updates → Update everything."
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Kirigami.Units.largeSpacing
                    rowSpacing: Kirigami.Units.smallSpacing

                    Controls.Label { text: "Type" }
                    Controls.ComboBox {
                        id: rdProtocol
                        Layout.fillWidth: true
                        model: [{text: "RDP (Windows, KDE/ReyOS)", value: "rdp"}, {text: "VNC", value: "vnc"}]
                        textRole: "text"
                        valueRole: "value"
                    }
                    Controls.Label { text: "Address" }
                    Controls.TextField {
                        id: rdHost
                        Layout.fillWidth: true
                        placeholderText: "e.g. my-pc or 192.168.1.20"
                        inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhUrlCharactersOnly
                        onAccepted: rdConnectButton.clicked()
                    }
                    Controls.Label { text: "Port" }
                    Controls.SpinBox {
                        id: rdPort
                        from: 1; to: 65535
                        editable: true
                        value: rdProtocol.currentValue === "vnc" ? 5900 : 3389
                        textFromValue: function(v) { return String(v) }
                    }
                    Controls.Label { text: "Username" }
                    Controls.TextField {
                        id: rdUser
                        Layout.fillWidth: true
                        placeholderText: "optional"
                        inputMethodHints: Qt.ImhNoAutoUppercase
                    }
                }

                RowLayout {
                    Controls.Button {
                        id: rdConnectButton
                        text: "Connect"
                        icon.name: "krdc"
                        enabled: rdClient && !rdBusy && rdHost.text.trim().length > 0
                        onClicked: connectTo(rdProtocol.currentValue, rdHost.text.trim(), rdPort.value, rdUser.text.trim())
                    }
                    Controls.BusyIndicator { running: rdBusy; visible: rdBusy; implicitHeight: rdConnectButton.implicitHeight }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    visible: rdMessage.length > 0
                    wrapMode: Text.Wrap
                    color: rdOk ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                    text: rdMessage
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: rdRecent.length > 0
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Heading { text: "Recent"; level: 4 }
                    Repeater {
                        model: rdRecent
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Controls.Label {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                text: (modelData.user ? modelData.user + "@" : "") + modelData.host + "  ·  " + modelData.protocol.toUpperCase() + " " + modelData.port
                            }
                            Controls.Button {
                                text: "Connect"
                                enabled: rdClient && !rdBusy
                                onClicked: connectTo(modelData.protocol, modelData.host, modelData.port, modelData.user || "")
                            }
                            Controls.ToolButton {
                                icon.name: "edit-delete-remove"
                                Controls.ToolTip.text: "Forget"
                                Controls.ToolTip.visible: hovered
                                onClicked: { backend.forgetRemoteDesktop(modelData.protocol, modelData.host, modelData.port, modelData.user || ""); refreshRemoteDesktop() }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: peerList.onlinePeers.length > 0
                    spacing: Kirigami.Units.smallSpacing
                    property var onlinePeers: (vpnInfo.tailscale && vpnInfo.tailscale.peers ? vpnInfo.tailscale.peers : []).filter(function(p) { return p.online && p.ip && p.os !== "iOS" && p.os !== "android" })
                    id: peerList
                    Kirigami.Heading { text: "Your Tailscale computers"; level: 4 }
                    Repeater {
                        model: peerList.onlinePeers
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { Layout.fillWidth: true; elide: Text.ElideRight; text: modelData.name + " (" + modelData.ip + ")" }
                            Controls.Button {
                                text: "Use"
                                onClicked: { rdHost.text = modelData.ip; rdHost.forceActiveFocus() }
                            }
                        }
                    }
                }
            }
        }

        ReyOSProgressBar { Layout.fillWidth: true; indeterminate: true; visible: busy }
        Controls.Label { id: statusLabel; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
