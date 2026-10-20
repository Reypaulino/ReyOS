import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Remote Desktop"

    property bool rdBusy: false
    property bool rdClient: false
    property var rdRecent: []
    property string rdMessage: ""
    property bool rdOk: false
    property var peers: []
    property var share: ({available: false, backendId: "", backend: "", enabled: false, active: false})
    property var sshInfo: ({installed: false, enabled: false, active: false})
    property bool x11: false
    property bool shareFirewallOpen: true
    readonly property var onlinePeers: peers.filter(function(p) { return p.online && p.ip && p.os !== "iOS" && p.os !== "android" })

    function refresh() {
        x11 = backend.sessionType() === "x11"
        rdClient = backend.remoteDesktopClientAvailable()
        rdRecent = backend.recentRemoteDesktops()
        share = backend.remoteDesktopStatus()
        shareFirewallOpen = backend.remoteDesktopFirewallOpen()
        sshInfo = backend.sshStatus()
        backend.refreshVpnStatus()
    }

    function connectTo(protocol, host, port, user) {
        rdBusy = true
        rdMessage = ""
        backend.connectRemoteDesktop(protocol, host, port, user)
    }

    Component.onCompleted: refresh()

    Connections {
        target: backend
        function onRemoteDesktopConnectFinished(ok, message) {
            page.rdBusy = false
            page.rdOk = ok
            page.rdMessage = message
            page.rdRecent = backend.recentRemoteDesktops()
        }
        function onVpnStatusReady(info) { page.peers = info.tailscale && info.tailscale.peers ? info.tailscale.peers : [] }
        function onActionFinished(ok, message) {
            page.share = backend.remoteDesktopStatus()
            page.shareFirewallOpen = backend.remoteDesktopFirewallOpen()
        }
    }

    actions: [
        Kirigami.Action { text: "Refresh"; icon.name: "view-refresh"; onTriggered: page.refresh() }
    ]

    Controls.Dialog {
        id: sshDialog
        title: "Connect with SSH"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Close
        property var info: ({user: "", hostname: "", addresses: []})
        width: Math.min(Kirigami.Units.gridUnit * 24, page.width - Kirigami.Units.gridUnit * 2)

        ColumnLayout {
            width: parent.width
            spacing: Kirigami.Units.smallSpacing
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: "From another device on the same network or VPN, run:"
            }
            Repeater {
                model: sshDialog.info.addresses
                delegate: Controls.TextField {
                    Layout.fillWidth: true
                    readOnly: true
                    selectByMouse: true
                    text: "ssh " + sshDialog.info.user + "@" + modelData
                }
            }
            Controls.Label {
                visible: sshDialog.info.addresses.length === 0
                opacity: 0.7
                wrapMode: Text.Wrap
                text: "No network address yet. Connect to Wi-Fi or the VPN first."
            }
        }
    }

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing * 2

        // -- Open another computer ------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            ColumnLayout {
                spacing: 2
                Kirigami.Heading { text: "Open another computer"; level: 2 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "See and control a Windows PC, another ReyOS/KDE or GNOME computer (RDP), or anything running VNC. Away from home? Connect the VPN first."
                }
            }

            Kirigami.InlineMessage {
                Layout.fillWidth: true
                visible: !page.rdClient
                type: Kirigami.MessageType.Warning
                text: "The remote desktop viewer (KRDC) isn't installed yet. Run Control Center → Updates → Update everything."
            }

            SectionCard {
                accented: true
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing

                    GridLayout {
                        Layout.fillWidth: true
                        columns: page.width > Kirigami.Units.gridUnit * 34 ? 4 : 2
                        columnSpacing: Kirigami.Units.largeSpacing
                        rowSpacing: Kirigami.Units.smallSpacing

                        Controls.Label { text: "Address" }
                        Controls.TextField {
                            id: rdHost
                            Layout.fillWidth: true
                            Layout.minimumWidth: Kirigami.Units.gridUnit * 8
                            placeholderText: "my-pc or 192.168.1.20"
                            inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhUrlCharactersOnly
                            onAccepted: if (connectButton.enabled) connectButton.clicked()
                        }
                        Controls.Label { text: "Type" }
                        Controls.ComboBox {
                            id: rdProtocol
                            Layout.fillWidth: true
                            model: [{text: "RDP", value: "rdp"}, {text: "VNC", value: "vnc"}]
                            textRole: "text"
                            valueRole: "value"
                        }
                        Controls.Label { text: "Username" }
                        Controls.TextField {
                            id: rdUser
                            Layout.fillWidth: true
                            placeholderText: "optional"
                            inputMethodHints: Qt.ImhNoAutoUppercase
                        }
                        Controls.Label { text: "Port" }
                        Controls.SpinBox {
                            id: rdPort
                            Layout.fillWidth: true
                            from: 1; to: 65535
                            editable: true
                            value: rdProtocol.currentValue === "vnc" ? 5900 : 3389
                            textFromValue: function(v) { return String(v) }
                        }
                    }

                    RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Button {
                            id: connectButton
                            text: "Connect"
                            icon.name: "network-connect"
                            highlighted: true
                            enabled: page.rdClient && !page.rdBusy && rdHost.text.trim().length > 0
                            onClicked: page.connectTo(rdProtocol.currentValue, rdHost.text.trim(), rdPort.value, rdUser.text.trim())
                        }
                        Controls.BusyIndicator {
                            running: page.rdBusy
                            visible: page.rdBusy
                            Layout.preferredHeight: connectButton.implicitHeight
                            Layout.preferredWidth: connectButton.implicitHeight
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            visible: page.rdMessage.length > 0
                            wrapMode: Text.Wrap
                            color: page.rdOk ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                            text: page.rdMessage
                        }
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.6
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        text: "The password is asked by the viewer, never stored by ReyOS Connect."
                    }
                }
            }

            SectionCard {
                visible: page.rdRecent.length > 0 || page.onlinePeers.length > 0
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.Heading { visible: page.rdRecent.length > 0; text: "Recent"; level: 4 }
                    Repeater {
                        model: page.rdRecent
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.largeSpacing
                            DeviceAvatar { iconName: "computer"; size: Kirigami.Units.iconSizes.medium + Kirigami.Units.smallSpacing * 2 }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Controls.Label { Layout.fillWidth: true; elide: Text.ElideRight; font.bold: true; text: modelData.host }
                                Controls.Label {
                                    opacity: 0.6
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    text: modelData.protocol.toUpperCase() + " · port " + modelData.port + (modelData.user ? " · " + modelData.user : "")
                                }
                            }
                            Controls.Button {
                                text: "Connect"
                                enabled: page.rdClient && !page.rdBusy
                                onClicked: page.connectTo(modelData.protocol, modelData.host, modelData.port, modelData.user || "")
                            }
                            Controls.ToolButton {
                                icon.name: "edit-delete-remove"
                                Controls.ToolTip.text: "Forget"
                                Controls.ToolTip.visible: hovered
                                onClicked: { backend.forgetRemoteDesktop(modelData.protocol, modelData.host, modelData.port, modelData.user || ""); page.rdRecent = backend.recentRemoteDesktops() }
                            }
                        }
                    }

                    Kirigami.Separator { Layout.fillWidth: true; visible: page.rdRecent.length > 0 && page.onlinePeers.length > 0 }
                    Kirigami.Heading { visible: page.onlinePeers.length > 0; text: "Your Tailscale computers"; level: 4 }
                    Repeater {
                        model: page.onlinePeers
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.largeSpacing
                            DeviceAvatar { iconName: "network-vpn"; size: Kirigami.Units.iconSizes.medium + Kirigami.Units.smallSpacing * 2 }
                            Controls.Label { Layout.fillWidth: true; elide: Text.ElideRight; text: modelData.name + "  ·  " + modelData.ip }
                            Controls.Button { text: "Use"; onClicked: { rdHost.text = modelData.ip; rdHost.forceActiveFocus() } }
                        }
                    }
                }
            }
        }

        // -- Share this computer --------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            ColumnLayout {
                spacing: 2
                Kirigami.Heading { text: "Share this computer"; level: 2 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "Let your phone or another computer see and control this desktop over RDP. Off by default; only reachable on your network or VPN."
                }
            }

            SectionCard {
                accented: page.share.active
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        DeviceAvatar { iconName: "computer"; size: Kirigami.Units.iconSizes.large; active: page.share.active }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Controls.Label { text: "Desktop sharing"; font.bold: true }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: !page.share.available ? "Not available: KDE's Remote Desktop server isn't installed."
                                    : page.share.backend
                            }
                        }
                        StatusPill {
                            visible: page.share.available
                            text: page.share.active ? "On" : "Off"
                            tone: page.share.active ? "positive" : "muted"
                        }
                    }

                    Kirigami.InlineMessage {
                        Layout.fillWidth: true
                        visible: page.share.available && page.x11 && page.share.backendId === "krdp"
                        type: Kirigami.MessageType.Information
                        text: "Sharing this desktop needs the Wayland session. Log out and pick “ReyOS Desktop”, or use RustDesk from Control Center on this session."
                        actions: [
                            Kirigami.Action { text: "Open Control Center"; icon.name: "configure"; onTriggered: backend.openControlCenter() }
                        ]
                    }

                    Kirigami.InlineMessage {
                        Layout.fillWidth: true
                        visible: page.share.available && !page.shareFirewallOpen
                        type: Kirigami.MessageType.Warning
                        text: "The firewall blocks desktop sharing (port 3389), so other devices can't connect. Allow it only if you want to share this desktop; the username and password below still protect it."
                        actions: [
                            Kirigami.Action { text: "Allow in firewall"; icon.name: "security-medium"; onTriggered: backend.openFirewallForRemoteDesktop() }
                        ]
                    }

                    Flow {
                        visible: page.share.available
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Button {
                            visible: !(page.x11 && page.share.backendId === "krdp") || page.share.active
                            text: page.share.active ? "Stop sharing" : "Start sharing"
                            icon.name: page.share.active ? "media-playback-stop" : "media-playback-start"
                            highlighted: !page.share.active
                            onClicked: page.share.active ? backend.stopRemoteDesktop() : backend.startRemoteDesktop()
                        }
                        Controls.Button {
                            text: "Username and password…"
                            icon.name: "configure"
                            onClicked: backend.openRemoteDesktopSettings()
                        }
                    }

                    Controls.Label {
                        visible: page.share.available
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.6
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        text: "Set a username and password first (KDE's own settings, stored in KWallet)."
                    }
                }
            }

            SectionCard {
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        DeviceAvatar { iconName: "utilities-terminal"; size: Kirigami.Units.iconSizes.large; active: page.sshInfo.active }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Controls.Label { text: "Terminal (SSH)"; font.bold: true }
                            Controls.Label {
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                opacity: 0.7
                                text: page.sshInfo.active ? "Listening on your network and VPN." : page.sshInfo.enabled ? "Enabled but not running." : "Off."
                            }
                        }
                        StatusPill { text: page.sshInfo.active ? "On" : "Off"; tone: page.sshInfo.active ? "positive" : "muted" }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Button {
                            visible: page.sshInfo.active
                            text: "How to connect"
                            icon.name: "help-about"
                            onClicked: { sshDialog.info = backend.sshConnectionInfo(); sshDialog.open() }
                        }
                        Controls.Button {
                            visible: !page.sshInfo.active
                            text: "Set up in Control Center"
                            icon.name: "configure"
                            onClicked: backend.openControlCenter()
                        }
                    }
                }
            }
        }
    }
}
