import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

// Remote Play (Sunshine + Moonlight): the same panel in Control Center's
// Gaming page and in ReyOS Games' "Play on another device" window. Talks to
// the `remotePlay` context object (remote_play_backend.py).
ColumnLayout {
    id: panel
    spacing: Kirigami.Units.largeSpacing

    // Control Center installs it and decides whether ReyOS Games shows it;
    // ReyOS Games only shows the panel once it's installed.
    property bool allowInstall: true
    property bool showGamesSwitch: true

    property var st: ({ installed: false, running: false, atLogin: false, local: [], tailscale: {},
                        firewallOpen: false, inputReady: true, showInGames: true })
    property bool busy: false
    property bool loaded: false
    property string progressLine: ""
    property var pending: []
    property var paired: []
    property string pairError: ""

    readonly property string mainAddress: st.local && st.local.length > 0 ? st.local[0].address : ""
    readonly property string tailscaleAddress: st.tailscale && st.tailscale.address ? st.tailscale.address : ""

    function refresh() { remotePlay.refresh() }

    Component.onCompleted: { busy = remotePlay.busy(); refresh() }

    Connections {
        target: remotePlay
        function onStatusReady(status) {
            st = status
            loaded = true
            if (st.running) remotePlay.loadPairings()
            else { pending = []; paired = []; pairError = "" }
        }
        function onBusyChanged(b) { busy = b; if (!b) progressLine = "" }
        function onProgress(line) { if (line.length > 0) progressLine = line }
        function onPairingsReady(p, d, error) { pending = p; paired = d; pairError = error }
        function onFinished(ok, message) { applicationWindow().notify(message, ok) }
    }

    // Changed elsewhere meanwhile (ReyOS Games, Moonlight): show it on return.
    Connections {
        target: Qt.application
        function onStateChanged() { if (Qt.application.state === Qt.ApplicationActive && panel.visible) refresh() }
    }

    // While it's on, look for devices asking to pair (Moonlight waits for
    // the PIN on its screen).
    Timer {
        interval: 3000
        repeat: true
        running: panel.visible && st.running && !busy
        onTriggered: remotePlay.loadPairings()
    }

    // What a slow step is doing (installing, waiting for Moonlight).
    RowLayout {
        visible: busy
        Layout.fillWidth: true
        Controls.BusyIndicator { running: busy; Layout.preferredWidth: Kirigami.Units.iconSizes.medium; Layout.preferredHeight: Kirigami.Units.iconSizes.medium }
        Controls.Label {
            Layout.fillWidth: true
            elide: Text.ElideRight
            opacity: 0.75
            text: progressLine !== "" ? progressLine : "Working..."
        }
    }

    // ---- not installed ----
    ColumnLayout {
        visible: loaded && !st.installed
        Layout.fillWidth: true
        spacing: Kirigami.Units.largeSpacing
        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: "Play this PC's games on your TV, phone or tablet with the free Moonlight app (Apple TV, iPhone, iPad, Android, other PCs). The game runs here; Moonlight shows it and sends your controller's buttons back."
        }
        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.75
            text: "Optional and off until you turn it on. Installs Sunshine (about 35 MB) from ReyOS's repo. Nothing is opened to the internet."
        }
        RowLayout {
            visible: allowInstall
            Controls.Button {
                text: "Install Remote Play"
                icon.name: "list-add"
                highlighted: true
                enabled: !busy
                onClicked: remotePlay.install()
            }
        }
    }

    // ---- installed ----
    ColumnLayout {
        visible: st.installed
        Layout.fillWidth: true
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                font.bold: true
                color: st.running ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.textColor
                text: st.running ? "On" + (mainAddress ? ": Moonlight finds this PC as " + mainAddress : "")
                                 : "Off: nothing can stream from this PC"
            }
            Controls.Button {
                text: st.running ? "Turn off" : "Turn on"
                icon.name: st.running ? "media-playback-stop" : "media-playback-start"
                highlighted: !st.running
                enabled: !busy
                onClicked: st.running ? remotePlay.turnOff() : remotePlay.turnOn()
            }
        }

        Controls.Switch {
            text: "Start Remote Play when I log in"
            checked: st.atLogin
            enabled: !busy
            onToggled: remotePlay.setStartsAtLogin(checked)
        }
        Controls.Switch {
            visible: showGamesSwitch
            text: "Show \"Play on another device\" in ReyOS Games"
            checked: st.showInGames
            enabled: !busy
            onToggled: remotePlay.setShowInGames(checked)
        }

        // A plain row: an InlineMessage's action button covers wrapped text.
        RowLayout {
            visible: !st.firewallOpen
            Layout.fillWidth: true
            Kirigami.Icon { source: "dialog-warning"; Layout.preferredWidth: Kirigami.Units.iconSizes.medium; Layout.preferredHeight: Kirigami.Units.iconSizes.medium }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: "The firewall blocks Moonlight. Allow it for your home network and Tailscale (asks for your password; the internet stays blocked)."
            }
            Controls.Button {
                text: "Allow"
                icon.name: "security-medium"
                enabled: !busy
                onClicked: remotePlay.allowNetwork(true)
            }
        }
        RowLayout {
            visible: st.firewallOpen
            Layout.fillWidth: true
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                opacity: 0.8
                text: "✓ Firewall: open to your home network and Tailscale only"
            }
            Controls.Button {
                text: "Block again"
                flat: true
                enabled: !busy
                onClicked: remotePlay.allowNetwork(false)
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: st.encoder !== undefined && st.encoder.software === true
            type: Kirigami.MessageType.Warning
            text: "No video encoder on this PC's graphics: the stream is encoded by the CPU, which is slower and makes the PC hotter. Use 720p and 30 or 60 FPS in Moonlight."
        }
        Controls.Label {
            Layout.fillWidth: true
            visible: st.encoder !== undefined && st.encoder.inUse !== "" && st.encoder.software !== true
            wrapMode: Text.Wrap
            opacity: 0.8
            text: "✓ Video: " + (st.encoder ? st.encoder.inUse : "") + " (the graphics chip encodes, not the CPU)"
        }
        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: !st.inputReady
            type: Kirigami.MessageType.Information
            text: "Restart the PC once so Moonlight's controller, mouse and keyboard can work here (Sunshine just installed their device rules)."
        }

        // Pairing requests: Moonlight shows a 4-digit PIN; type it here.
        Repeater {
            model: pending
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        font.bold: true
                        text: (modelData.name || "A device") + " (" + modelData.address + ") wants to stream from this PC"
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "Type the PIN shown on its screen. Only pair devices you own: a paired device can control this PC."
                    }
                    RowLayout {
                        Controls.TextField {
                            id: pinField
                            placeholderText: "PIN"
                            maximumLength: 4
                            inputMethodHints: Qt.ImhDigitsOnly
                            validator: RegularExpressionValidator { regularExpression: /[0-9]{0,4}/ }
                            Layout.preferredWidth: Kirigami.Units.gridUnit * 5
                            onAccepted: if (text.length === 4) remotePlay.pair(modelData.id, text, nameField.text)
                        }
                        Controls.TextField {
                            id: nameField
                            placeholderText: "Name"
                            text: modelData.name || ""
                            Layout.fillWidth: true
                        }
                        Controls.Button {
                            text: "Pair"
                            highlighted: true
                            enabled: !busy && pinField.text.length === 4
                            onClicked: remotePlay.pair(modelData.id, pinField.text, nameField.text)
                        }
                        Controls.Button {
                            text: "Decline"
                            flat: true
                            enabled: !busy
                            onClicked: remotePlay.decline(modelData.id)
                        }
                    }
                }
            }
        }

        ColumnLayout {
            visible: st.running && paired.length > 0
            Layout.fillWidth: true
            spacing: 0
            Controls.Label { text: "Paired devices"; font.bold: true }
            Repeater {
                model: paired
                delegate: RowLayout {
                    Layout.fillWidth: true
                    Controls.Label { Layout.fillWidth: true; text: modelData.name || "Unnamed device"; elide: Text.ElideRight }
                    Controls.Button {
                        text: "Remove"
                        flat: true
                        enabled: !busy
                        onClicked: remotePlay.unpair(modelData.uuid)
                    }
                }
            }
        }
        Controls.Label {
            visible: st.running && pairError !== ""
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: Kirigami.Theme.negativeTextColor
            text: pairError
        }

        // How to connect
        Controls.Label { text: "How to connect"; font.bold: true }
        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            textFormat: Text.StyledText
            text: "<b>Apple TV / iPhone / iPad:</b> install Moonlight from the App Store, on the same Wi-Fi as this PC. "
                  + "This PC shows up by itself (or press + and type " + (mainAddress || "this PC's address") + "). "
                  + "Pick it: Moonlight shows a PIN, and the request appears here. Then pick Desktop or ReyOS Games.<br>"
                  + "<b>Controller:</b> pair it with the Apple TV or iPhone (Bluetooth settings there), not with this PC. "
                  + "Moonlight sends its buttons here as a controller your games already know.<br>"
                  + "<b>Picture:</b> in Moonlight's settings start with 720p or 1080p, 60 FPS, 8–12 Mbps, H.264.<br>"
                  + "<b>Away from home:</b> sign in to Tailscale here (ReyOS Connect → VPN) and in the Tailscale app on the phone, then add "
                  + (tailscaleAddress ? tailscaleAddress : "this PC's Tailscale address") + " in Moonlight. No router ports are opened."
        }
        Controls.Label {
            visible: !!(st.tailscale && st.tailscale.peers && st.tailscale.peers.length > 0)
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.8
            text: st.tailscale && st.tailscale.peers
                  ? "Tailscale devices online: " + st.tailscale.peers.map(function (p) {
                        return p.name + (p.path === "relayed" ? " (relayed: slower)" : p.path === "direct" ? " (direct)" : "") }).join(", ")
                  : ""
        }

        Flow {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            Controls.Button {
                text: "Sunshine settings"
                icon.name: "configure"
                flat: true
                enabled: st.running
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Opens Sunshine's own settings in the browser (only on this PC). Sign in as \"reyos\" with Copy password."
                onClicked: remotePlay.openSettings()
            }
            Controls.Button {
                text: "Copy password"
                icon.name: "edit-copy"
                flat: true
                onClicked: remotePlay.copyPassword()
            }
            Controls.Button {
                text: "Copy diagnostics"
                icon.name: "tools-report-bug"
                flat: true
                onClicked: remotePlay.copyDiagnostics()
            }
            Controls.Button {
                text: "Check again"
                icon.name: "view-refresh"
                flat: true
                onClicked: refresh()
            }
        }
    }
}
