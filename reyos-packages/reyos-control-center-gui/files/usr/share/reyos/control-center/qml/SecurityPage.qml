import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Security"

    property bool busy: false
    property bool firewallEnabled: false
    property string vpnActive: ""
    property int vpnProfileCount: 0
    property int shieldsBlocked: 0
    property bool usbGuardEnabled: false

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshSecurityOverview()
        backend.refreshUsbGuardStatus()
    }

    Connections {
        target: backend
        function onSecurityOverviewReady(info) {
            busy = false
            firewallEnabled = info.firewallEnabled
            vpnActive = info.vpnActive || ""
            vpnProfileCount = info.vpnProfileCount
            shieldsBlocked = info.shieldsBlocked
        }
        function onUsbGuardStatusReady(info) {
            usbGuardEnabled = info.enabled
        }
        function onActionFinished(ok, message) {
            busy = false
            usbGuardStatusLabel.text = message
            usbGuardStatusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: "Everything ReyOS's \"safe by default\" pitch depends on, in one place."
        }

        GridLayout {
            Layout.fillWidth: true
            columns: width > Kirigami.Units.gridUnit * 40 ? 3 : (width > Kirigami.Units.gridUnit * 24 ? 2 : 1)
            columnSpacing: Kirigami.Units.gridUnit
            rowSpacing: Kirigami.Units.gridUnit

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "security-medium"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "Firewall"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: firewallEnabled ? "Active" : "Inactive"
                        color: firewallEnabled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                        font.bold: true
                    }
                    Controls.Button {
                        text: "Open Firewall"
                        Layout.alignment: Qt.AlignLeft
                        onClicked: applicationWindow().openReyosPage("FirewallPage.qml")
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "network-vpn"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "VPN"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: vpnActive.length > 0 ? ("Connected: " + vpnActive) : (vpnProfileCount > 0 ? "Not connected" : "No profiles imported")
                        color: vpnActive.length > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                    }
                    Controls.Button {
                        text: "Open VPN"
                        Layout.alignment: Qt.AlignLeft
                        onClicked: applicationWindow().openReyosPage("VpnPage.qml")
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "view-private"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "Browser Shields"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: shieldsBlocked > 0 ? (shieldsBlocked + " trackers/ads blocked, lifetime") : "No data yet — open ReyOS Browser"
                        color: shieldsBlocked > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "object-locked"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "Permissions"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: "File ownership & access fixes"
                        opacity: 0.7
                        wrapMode: Text.Wrap
                    }
                    Controls.Button {
                        text: "Open Permissions"
                        Layout.alignment: Qt.AlignLeft
                        onClicked: applicationWindow().openReyosPage("PermissionsPage.qml")
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "drive-removable-media-usb"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "USB Protection"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: usbGuardEnabled ? "Blocking unrecognized USB devices" : "Off — any USB device is allowed"
                        color: usbGuardEnabled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Guards against malicious USB devices (BadUSB). Off by default so plugging in a flash drive just works."
                    }
                    Controls.Button {
                        text: usbGuardEnabled ? "Disable USB protection" : "Enable USB protection"
                        Layout.alignment: Qt.AlignLeft
                        enabled: !busy
                        onClicked: {
                            busy = true
                            if (usbGuardEnabled) backend.disableUsbGuard()
                            else backend.enableUsbGuard()
                        }
                    }
                }
            }
        }

        Controls.Label {
            id: usbGuardStatusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        // The page's Refresh action renders as a fixed bottom toolbar
        // (Kirigami's contextual-actions bar) that sits on top of the
        // scrollable content rather than reserving its own space -- without
        // this, the last row of cards ends up partly hidden behind it.
        Item { Layout.fillWidth: true; Layout.preferredHeight: Kirigami.Units.gridUnit * 3 }
    }
}
