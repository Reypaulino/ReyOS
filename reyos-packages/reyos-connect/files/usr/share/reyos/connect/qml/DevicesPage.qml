import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Devices"

    property var devices: []
    property var customDevices: []
    property bool helpOpen: false

    readonly property var win: applicationWindow()
    readonly property bool ready: win.kdeconnectInstalled && win.backendAvailable
    readonly property var paired: devices.filter(function(d) { return d.isPaired })
    readonly property var requests: devices.filter(function(d) { return !d.isPaired && d.state === "pairingIncoming" })
    readonly property var nearby: devices.filter(function(d) { return !d.isPaired && d.state !== "pairingIncoming" })
    readonly property int connectedCount: paired.filter(function(d) { return d.state === "connected" }).length
    readonly property int tileColumns: Math.max(1, Math.floor(width / (Kirigami.Units.gridUnit * 22)))

    function refresh() {
        devices = win.backendAvailable ? backend.listDevices() : []
        customDevices = backend.listCustomDevices()
    }

    Component.onCompleted: refresh()

    Connections {
        target: backend
        function onDevicesChanged() { page.refresh() }
        function onBackendAvailableChanged(available) { page.refresh() }
    }

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            enabled: page.win.backendAvailable
            onTriggered: { backend.refreshDiagnostics(); page.refresh() }
        }
    ]

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing * 2

        // -- KDE Connect missing / not running -------------------------------
        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.gridUnit * 3
            visible: !page.win.kdeconnectInstalled
            icon.name: "dialog-warning"
            text: "KDE Connect is required for ReyOS Connect."
            explanation: "The kdeconnect package could not be found. Run Control Center → Updates → Update everything to bring it back."
        }
        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.gridUnit * 3
            visible: page.win.kdeconnectInstalled && !page.win.backendAvailable
            icon.name: "network-disconnect"
            text: "KDE Connect isn't running"
            explanation: "It normally starts automatically when you log in."
            helpfulAction: Kirigami.Action {
                text: "Start KDE Connect"
                icon.name: "media-playback-start"
                onTriggered: backend.startDaemon()
            }
        }

        // -- Summary -------------------------------------------------------------
        RowLayout {
            visible: page.ready
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Kirigami.Heading {
                    level: 1
                    text: page.paired.length === 0 ? "Connect your phone"
                        : page.connectedCount === 1 ? "1 device connected"
                        : page.connectedCount + " devices connected"
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: page.win.diagnostics.selfName
                        ? "Other devices see this computer as “" + page.win.diagnostics.selfName + "”."
                        : "Share files, links and your clipboard with your phone, and use it as a remote."
                }
            }
        }

        // -- Pairing requests (always first: someone is waiting) ------------------
        Repeater {
            model: page.ready ? page.requests : []
            delegate: SectionCard {
                accented: true
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    DeviceAvatar { iconName: modelData.statusIconName || "smartphone"; size: Kirigami.Units.iconSizes.large }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Kirigami.Heading { level: 3; text: (modelData.name || "A device") + " wants to pair"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        Controls.Label { opacity: 0.7; Layout.fillWidth: true; wrapMode: Text.Wrap; text: "Only accept if you started pairing on that device." }
                    }
                    Controls.Button { text: "Accept"; highlighted: true; icon.name: "dialog-ok"; onClicked: backend.acceptPairing(modelData.id) }
                    Controls.Button { text: "Reject"; icon.name: "dialog-cancel"; onClicked: backend.rejectPairing(modelData.id) }
                }
            }
        }

        // -- My devices -------------------------------------------------------------
        ColumnLayout {
            visible: page.ready
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading { text: "My devices"; level: 2 }
                StatusPill { visible: page.paired.length > 0; text: String(page.paired.length); tone: "accent" }
                Item { Layout.fillWidth: true }
            }

            GridLayout {
                visible: page.paired.length > 0
                Layout.fillWidth: true
                columns: page.tileColumns
                columnSpacing: Kirigami.Units.largeSpacing
                rowSpacing: Kirigami.Units.largeSpacing
                Repeater {
                    model: page.paired
                    delegate: DeviceTile {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.alignment: Qt.AlignTop
                        device: modelData
                        onOpenRequested: page.win.openDevice(modelData.id)
                    }
                }
            }

            SectionCard {
                visible: page.paired.length === 0
                contentItem: RowLayout {
                    spacing: Kirigami.Units.gridUnit
                    DeviceAvatar { iconName: "smartphone"; active: false; Layout.alignment: Qt.AlignTop }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Kirigami.Heading { level: 3; text: "No paired devices yet" }
                        Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "1. Install KDE Connect on your phone (App Store or Google Play)." }
                        Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "2. Connect the phone to the same Wi-Fi as this computer." }
                        Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "3. Your phone shows up under Nearby below. Press Pair and approve it on the phone." }
                    }
                }
            }
        }

        // -- Nearby -----------------------------------------------------------------
        ColumnLayout {
            visible: page.ready
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading { text: "Nearby"; level: 2 }
                Controls.Label { text: "Not paired yet"; opacity: 0.6 }
                Item { Layout.fillWidth: true }
            }

            SectionCard {
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing

                    Repeater {
                        model: page.nearby
                        delegate: ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.largeSpacing
                                DeviceAvatar { iconName: modelData.statusIconName || "smartphone"; size: Kirigami.Units.iconSizes.large; active: false }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Controls.Label { Layout.fillWidth: true; text: modelData.name || "Unknown device"; font.bold: true; elide: Text.ElideRight }
                                    Controls.Label {
                                        opacity: 0.6
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                                        text: modelData.state === "pairingOutgoing" ? "Waiting for approval on the device…"
                                            : modelData.state === "available" ? "Ready to pair" : "Out of reach"
                                    }
                                }
                                Controls.Button {
                                    visible: modelData.state === "available"
                                    text: "Pair"
                                    icon.name: "network-connect"
                                    highlighted: true
                                    onClicked: backend.requestPairing(modelData.id)
                                }
                                Controls.BusyIndicator {
                                    visible: modelData.state === "pairingOutgoing"
                                    running: visible
                                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                                }
                            }
                            Kirigami.Separator { Layout.fillWidth: true; visible: index < page.nearby.length - 1 }
                        }
                    }

                    RowLayout {
                        visible: page.nearby.length === 0
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Controls.BusyIndicator {
                            running: page.visible
                            Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: 0.7
                            text: "Looking for devices… Open KDE Connect on your phone and make sure it's on the same network."
                        }
                    }
                }
            }
        }

        // -- Help (folded away until needed) -------------------------------------------
        SectionCard {
            visible: page.win.kdeconnectInstalled
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Controls.ItemDelegate {
                    Layout.fillWidth: true
                    leftPadding: 0
                    rightPadding: 0
                    icon.name: page.helpOpen ? "go-down" : "go-next"
                    text: "Can't find your phone?"
                    font.bold: true
                    onClicked: {
                        page.helpOpen = !page.helpOpen
                        if (page.helpOpen) backend.refreshDiagnostics()
                    }
                }

                ColumnLayout {
                    visible: page.helpOpen
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "1. Make sure ReyOS and your phone are on the same network." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "2. Open KDE Connect on the phone." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "3. Check that the firewall lets KDE Connect through." }
                    Controls.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: "4. On a different network (VPN, hotspot)? Add the phone's IP address below." }

                    Controls.Label {
                        Layout.fillWidth: true
                        Layout.topMargin: Kirigami.Units.smallSpacing
                        wrapMode: Text.Wrap
                        visible: page.win.diagnostics.daemonRunning !== undefined
                        opacity: 0.8
                        text: {
                            var d = page.win.diagnostics
                            var lines = ["KDE Connect service: " + (d.daemonRunning ? "running" : "stopped")]
                            if (d.firewallDetail) lines.push(d.firewallDetail)
                            return lines.join("\n")
                        }
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Button { text: "Check again"; icon.name: "view-refresh"; onClicked: backend.refreshDiagnostics() }
                        Controls.Button {
                            text: "Allow in firewall"
                            icon.name: "security-medium"
                            visible: page.win.diagnostics.firewallOpen === false
                            onClicked: page.win.askFirewall()
                        }
                        Controls.Button { text: "Full diagnostics"; icon.name: "system-search"; onClicked: page.win.openSection("diagnostics") }
                    }

                    Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }
                    Kirigami.Heading { text: "Connect by IP address"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "KDE Connect finds devices by broadcasting on the local network. If your phone is reachable but on a different network segment, add its IP address here."
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Controls.TextField {
                            id: customIpField
                            Layout.fillWidth: true
                            placeholderText: "192.168.1.42"
                            onAccepted: { backend.addCustomDevice(text); text = "" }
                        }
                        Controls.Button {
                            text: "Add"
                            icon.name: "list-add"
                            onClicked: { backend.addCustomDevice(customIpField.text); customIpField.text = "" }
                        }
                    }
                    Repeater {
                        model: page.customDevices
                        delegate: RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { Layout.fillWidth: true; text: modelData }
                            Controls.Button { text: "Remove"; icon.name: "edit-delete-remove"; onClicked: backend.removeCustomDevice(modelData) }
                        }
                    }
                }
            }
        }
    }
}
