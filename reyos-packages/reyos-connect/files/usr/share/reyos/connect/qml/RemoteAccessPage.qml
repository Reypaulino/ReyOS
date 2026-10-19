import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "VPN"

    property var vpnInfo: ({backends: {}, tailscale: {}, wireguard: {}})
    property string selectedBackend: "tailscale"
    property var testChecks: []
    property bool testReady: false
    property bool testRun: false
    property bool busy: false
    property bool signingIn: false
    property string signInUrl: ""
    readonly property bool hasTailscale: !!(vpnInfo.backends && vpnInfo.backends.tailscale)
    readonly property bool hasWireguard: !!(vpnInfo.backends && vpnInfo.backends.wireguard)
    readonly property var ts: vpnInfo.tailscale || {}
    readonly property var wgInterfaces: (vpnInfo.wireguard && vpnInfo.wireguard.interfaces) ? vpnInfo.wireguard.interfaces : []

    function refresh() { busy = true; backend.refreshVpnStatus() }

    Component.onCompleted: refresh()

    Connections {
        target: backend
        function onVpnStatusReady(info) {
            page.busy = false
            page.vpnInfo = info
            if (page.selectedBackend === "tailscale" && !page.hasTailscale && page.hasWireguard) page.selectedBackend = "wireguard"
            else if (page.selectedBackend === "wireguard" && !page.hasWireguard && page.hasTailscale) page.selectedBackend = "tailscale"
        }
        function onRemoteConnectionTestReady(result) {
            page.busy = false
            page.testChecks = (result && result.checks) ? result.checks : []
            page.testReady = !!(result && result.ready)
            page.testRun = true
        }
        function onActionFinished(ok, message) { page.refresh() }
        function onTailscaleSignInUrl(url) { page.signInUrl = url }
        function onTailscaleSignInFinished(ok, message) {
            page.signingIn = false
            page.signInUrl = ""
            applicationWindow().showPassiveNotification(message, "long")
            page.refresh()
        }
    }

    actions: [
        Kirigami.Action { text: "Refresh"; icon.name: "view-refresh"; onTriggered: page.refresh() }
    ]

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        ColumnLayout {
            spacing: 2
            Kirigami.Heading { text: "Reach your devices away from home"; level: 2 }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                opacity: 0.7
                text: "A VPN puts your phone and this computer on one private network wherever they are, so pairing, remote desktop and SSH keep working."
            }
        }

        ReyOSProgressBar { Layout.fillWidth: true; indeterminate: true; visible: page.busy }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: !page.busy && !page.hasTailscale && !page.hasWireguard
            type: Kirigami.MessageType.Information
            text: "No VPN set up yet. Install Tailscale, or add a WireGuard profile in Control Center."
            actions: [
                Kirigami.Action { text: "Open Control Center"; icon.name: "configure"; onTriggered: backend.openControlCenter() }
            ]
        }

        SectionCard {
            visible: page.hasTailscale || page.hasWireguard
            accented: page.selectedBackend === "tailscale" ? !!page.ts.connected : page.wgInterfaces.some(function(i) { return i.active })
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                RowLayout {
                    visible: page.hasTailscale && page.hasWireguard
                    Controls.TabBar {
                        Controls.TabButton { text: "Tailscale"; checked: page.selectedBackend === "tailscale"; onClicked: page.selectedBackend = "tailscale"; width: implicitWidth }
                        Controls.TabButton { text: "WireGuard"; checked: page.selectedBackend === "wireguard"; onClicked: page.selectedBackend = "wireguard"; width: implicitWidth }
                    }
                }

                // -- Tailscale --
                ColumnLayout {
                    visible: page.selectedBackend === "tailscale" && page.hasTailscale
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        DeviceAvatar { iconName: "network-vpn"; size: Kirigami.Units.iconSizes.large; active: !!page.ts.connected }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Controls.Label { text: "Tailscale"; font.bold: true }
                            Controls.Label {
                                opacity: 0.7
                                text: page.ts.selfIp ? "This computer: " + page.ts.selfIp : "No address yet"
                            }
                        }
                        StatusPill {
                            text: page.ts.connected ? "Connected" : !page.ts.serviceActive ? "Off"
                                : page.ts.authenticated ? "Not connected" : "Not signed in"
                            tone: page.ts.connected ? "positive" : "muted"
                        }
                    }

                    // Off, or set up outside ReyOS Connect: one password prompt.
                    ColumnLayout {
                        visible: !page.ts.serviceActive || !page.ts.canControl
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: 0.8
                            text: !page.ts.serviceActive
                                ? "Tailscale puts this computer, your phone and your other computers on one private network, wherever they are. It's off until you set it up. You need a free Tailscale account, and the Tailscale app on your phone."
                                : "Tailscale was set up outside ReyOS Connect. Set it up here once so you can sign in, connect and disconnect from this page."
                        }
                        Controls.Button {
                            text: "Set up Tailscale"
                            icon.name: "network-vpn"
                            highlighted: true
                            enabled: !page.busy
                            onClicked: { page.busy = true; backend.setupTailscale() }
                        }
                        Controls.Label {
                            opacity: 0.6
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            text: "Asks for your password once."
                        }
                    }

                    // On, not signed in yet.
                    ColumnLayout {
                        visible: page.ts.serviceActive && page.ts.canControl && !page.ts.authenticated
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: 0.8
                            text: page.signingIn
                                ? "Finish signing in in your browser. This page updates by itself when you're done."
                                : "Sign in with your Tailscale account to add this computer to your Tailscale network."
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Button {
                                visible: !page.signingIn
                                text: "Sign in"
                                icon.name: "go-next"
                                highlighted: true
                                onClicked: { page.signingIn = true; backend.signInTailscale() }
                            }
                            Controls.Button {
                                visible: page.signingIn && page.signInUrl !== ""
                                text: "Open the sign-in page again"
                                icon.name: "internet-web-browser"
                                onClicked: Qt.openUrlExternally(page.signInUrl)
                            }
                            Controls.Button {
                                visible: page.signingIn
                                text: "Cancel"
                                onClicked: backend.cancelTailscaleSignIn()
                            }
                            Controls.BusyIndicator {
                                visible: page.signingIn
                                running: visible
                                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                            }
                        }
                    }

                    // Signed in.
                    Controls.Button {
                        visible: page.ts.serviceActive && page.ts.canControl && !!page.ts.authenticated
                        text: page.ts.connected ? "Disconnect" : "Connect"
                        icon.name: page.ts.connected ? "network-disconnect" : "network-connect"
                        highlighted: !page.ts.connected
                        enabled: !page.busy
                        onClicked: { page.busy = true; backend.setTailscaleConnected(!page.ts.connected) }
                    }
                    ColumnLayout {
                        visible: !!page.ts.peers && page.ts.peers.length > 0
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Kirigami.Separator { Layout.fillWidth: true }
                        Kirigami.Heading { text: "On your Tailscale network"; level: 4 }
                        Repeater {
                            model: page.ts.peers || []
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: modelData.online ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                                }
                                Controls.Label { Layout.fillWidth: true; elide: Text.ElideRight; text: modelData.name }
                                Controls.Label { opacity: 0.6; text: modelData.ip || "" }
                                Controls.Label { opacity: 0.6; text: modelData.online ? "online" : "offline" }
                            }
                        }
                    }
                }

                // -- WireGuard --
                ColumnLayout {
                    visible: page.selectedBackend === "wireguard" && page.hasWireguard
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Label { text: "WireGuard"; font.bold: true }
                    Controls.Label {
                        visible: !!page.vpnInfo.wireguard && !page.vpnInfo.wireguard.profilesReadable
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Some profiles may not be listed: /etc/wireguard needs administrator access. Manage profiles in Control Center."
                    }
                    Repeater {
                        model: page.wgInterfaces
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { Layout.fillWidth: true; text: modelData.name }
                            StatusPill { text: modelData.active ? "Connected" : "Off"; tone: modelData.active ? "positive" : "muted" }
                            Controls.Button {
                                text: modelData.active ? "Disconnect" : "Connect"
                                enabled: !page.busy
                                onClicked: {
                                    page.busy = true
                                    if (modelData.active) backend.disconnectWireguard(modelData.name, modelData.source)
                                    else backend.connectWireguard(modelData.name, modelData.source)
                                }
                            }
                        }
                    }
                    Controls.Label {
                        visible: page.wgInterfaces.length === 0
                        opacity: 0.6
                        text: "No WireGuard profiles found."
                    }
                }

                Controls.Button {
                    visible: page.selectedBackend === "tailscale" && !!page.ts.serviceActive
                    text: "Turn off Tailscale"
                    icon.name: "system-shutdown"
                    flat: true
                    enabled: !page.busy && !page.signingIn
                    onClicked: { page.busy = true; backend.turnOffTailscale() }
                }
                Controls.Button {
                    text: "VPN settings (Control Center)"
                    icon.name: "configure"
                    flat: true
                    onClicked: backend.openControlCenter()
                }
            }
        }

        SectionCard {
            visible: page.hasTailscale || page.hasWireguard
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Test the connection"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "Checks the VPN, that your phone is reachable through it, and SSH."
                }
                Controls.Button {
                    text: "Run test"
                    icon.name: "system-run"
                    enabled: !page.busy
                    onClicked: { page.busy = true; page.testRun = false; page.testChecks = []; backend.testRemoteConnection(page.selectedBackend, "", true) }
                }
                Repeater {
                    model: page.testChecks
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { Layout.fillWidth: true; text: modelData.check; font.bold: true }
                            StatusPill { text: modelData.passed ? "Pass" : "Fail"; tone: modelData.passed ? "positive" : "negative" }
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: 0.7
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            text: modelData.detail
                        }
                    }
                }
                Controls.Label {
                    visible: page.testRun
                    font.bold: true
                    color: page.testReady ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
                    text: page.testReady ? "Remote access is ready." : "Not ready yet; see the checks above."
                }
            }
        }
    }
}
