import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Network"

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    property bool loading: false
    property bool wgBusy: false

    function refresh() {
        loading = true
        backend.refreshNetworkInfo()
        backend.refreshWireguardStatus()
    }

    Connections {
        target: backend
        function onNetworkInfoReady(info) {
            loading = false
            addrModel.clear()
            // Plain words: what kind of connection, its address and the
            // router's, not "lo" or a raw route line.
            for (var i = 0; i < info.addresses.length; i++) {
                var a = info.addresses[i]
                if (a.iface === "lo") continue
                var kind = /^wl/.test(a.iface) ? "Wi-Fi" : /^(en|eth)/.test(a.iface) ? "Wired (Ethernet)"
                         : /^(wg|tun|tap)/.test(a.iface) ? "VPN" : a.iface
                if (a.address.indexOf(":") >= 0) continue  // IPv6: keep the list short
                addrModel.append({ iface: kind, address: a.address.split("/")[0] })
            }
            var m = /via (\S+)/.exec(info.gateway || "")
            gatewayLabel.text = m ? m[1] : "Not connected"
            portsModel.clear()
            for (var j = 0; j < info.ports.length; j++) portsModel.append(info.ports[j])
        }
        function onWireguardListed(conns) {
            wgModel.clear()
            for (var k = 0; k < conns.length; k++) wgModel.append(conns[k])
        }
        function onActionFinished(ok, message) {
            wgBusy = false
            if (message.length > 0) {
                wgStatusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
                wgStatusLabel.color = Kirigami.Theme.negativeTextColor
            }
            if (ok) backend.refreshWireguardStatus()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: addrModel }
    ListModel { id: portsModel }
    ListModel { id: wgModel }

    Controls.Dialog {
        id: confirmRemoveWg
        title: "Remove WireGuard profile"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingName: ""
        onAccepted: { wgBusy = true; backend.removeWireguard(pendingName) }
        Controls.Label {
            text: "Remove WireGuard profile \"" + confirmRemoveWg.pendingName + "\"? This deletes its stored configuration, including the private key."
            wrapMode: Text.Wrap
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: loading
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Your connection"; level: 3 }
                Controls.Label {
                    visible: addrModel.count === 0 && !loading
                    text: "Not connected to a network."
                    opacity: 0.7
                }
                GridLayout {
                    columns: 2
                    columnSpacing: Kirigami.Units.gridUnit
                    rowSpacing: Kirigami.Units.smallSpacing
                    Repeater {
                        model: addrModel
                        delegate: Controls.Label { Layout.row: index; Layout.column: 0; text: iface; font.bold: true }
                    }
                    Repeater {
                        model: addrModel
                        delegate: Controls.Label { Layout.row: index; Layout.column: 1; text: "This computer: " + address }
                    }
                    Controls.Label { Layout.row: addrModel.count; Layout.column: 0; text: "Router"; font.bold: true }
                    Controls.Label { id: gatewayLabel; Layout.row: addrModel.count; Layout.column: 1 }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Open ports"; level: 3; Layout.fillWidth: true }
                    Controls.Button {
                        text: portsList.visible ? "Hide" : "Show"
                        onClicked: portsList.visible = !portsList.visible
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "Programs on this computer waiting for connections. For troubleshooting; the firewall decides who can reach them."
                }
                ColumnLayout {
                    id: portsList
                    visible: false
                Repeater {
                    model: portsModel
                    delegate: RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Label { text: proto; Layout.preferredWidth: 60 }
                        Controls.Label { text: address }
                    }
                }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "WireGuard VPN"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Button {
                        text: "Import configuration…"
                        enabled: !wgBusy
                        onClicked: { wgBusy = true; backend.importWireguardConfig() }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Import a WireGuard configuration from your VPN provider, workplace, or your own server. ReyOS does not operate a VPN service—you choose who you trust."
                }

                Repeater {
                    model: wgModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Label { text: name; font.bold: active; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.Label { visible: active; text: "connected"; color: Kirigami.Theme.positiveTextColor }
                        Controls.Button {
                            text: active ? "Disconnect" : "Connect"
                            enabled: !wgBusy
                            onClicked: {
                                wgBusy = true
                                if (active) backend.disconnectWireguard(name)
                                else backend.connectWireguard(name)
                            }
                        }
                        Controls.Button {
                            text: "Remove"
                            enabled: !wgBusy
                            onClicked: { confirmRemoveWg.pendingName = name; confirmRemoveWg.open() }
                        }
                    }
                }
                Controls.Label {
                    visible: wgModel.count === 0
                    text: "No WireGuard profiles imported yet."
                    opacity: 0.7
                }

                ReyOSProgressBar {
                    Layout.fillWidth: true
                    indeterminate: true
                    visible: wgBusy
                }
                Controls.Label {
                    id: wgStatusLabel
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }

                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.75
                    text: "Tip: a profile whose AllowedIPs includes 0.0.0.0/0 and ::/0 routes all internet traffic through the VPN. Do not share configuration files: they contain a private key."
                }
            }
        }
    }
}