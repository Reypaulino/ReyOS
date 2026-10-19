import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

// A paired device: who it is, whether it's reachable, battery, and the actions people use most.
SectionCard {
    id: tile
    property var device: ({})
    readonly property bool connected: device.state === "connected"
    readonly property var plugins: device.loadedPlugins || []

    signal openRequested()

    accented: connected

    TapHandler { onTapped: tile.openRequested() }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            DeviceAvatar {
                iconName: device.statusIconName || (device.type === "desktop" || device.type === "laptop" ? "computer" : device.type === "tablet" ? "tablet" : "smartphone")
                active: tile.connected
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading {
                    Layout.fillWidth: true
                    level: 2
                    text: device.name || "Unknown device"
                    elide: Text.ElideRight
                }
                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    StatusPill {
                        text: tile.connected ? "Connected" : "Not reachable"
                        tone: tile.connected ? "positive" : "muted"
                    }
                    Controls.Label {
                        visible: !!device.ipAddress && tile.connected
                        text: device.ipAddress || ""
                        opacity: 0.6
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                }
                RowLayout {
                    visible: !!device.battery
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon {
                        source: device.battery && device.battery.isCharging ? "battery-charging" : "battery"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }
                    ReyOSProgressBar {
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 6
                        value: device.battery ? device.battery.charge / 100 : 0
                    }
                    Controls.Label {
                        text: device.battery ? (device.battery.charge + "%" + (device.battery.isCharging ? " · charging" : "")) : ""
                        opacity: 0.75
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                }
                Controls.Label {
                    visible: !tile.connected
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.6
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    text: "Open KDE Connect on it and join the same network or VPN."
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Controls.Button {
                visible: tile.connected && tile.plugins.indexOf("kdeconnect_share") !== -1
                text: "Send file"
                icon.name: "document-send"
                onClicked: backend.openFilePickerAndSend(device.id)
            }
            Controls.Button {
                visible: tile.connected && tile.plugins.indexOf("kdeconnect_findmyphone") !== -1
                text: "Find phone"
                icon.name: "audio-volume-high"
                onClicked: backend.ringDevice(device.id)
            }
            Controls.Button {
                visible: tile.connected && tile.plugins.indexOf("kdeconnect_ping") !== -1
                text: "Ping"
                icon.name: "network-connect"
                onClicked: backend.pingDevice(device.id)
            }
            Controls.Button {
                text: "Open"
                icon.name: "go-next"
                highlighted: true
                onClicked: tile.openRequested()
            }
        }
    }
}
