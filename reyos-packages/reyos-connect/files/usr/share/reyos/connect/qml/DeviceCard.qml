import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.AbstractCard {
    id: card
    property var deviceData: ({})

    signal pairRequested()
    signal acceptRequested()
    signal rejectRequested()
    signal openRequested()
    signal sendFileRequested()

    Layout.fillWidth: true
    padding: Kirigami.Units.gridUnit

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Icon {
                source: deviceData.statusIconName || "smartphone"
                Layout.preferredWidth: Kirigami.Units.iconSizes.large
                Layout.preferredHeight: Kirigami.Units.iconSizes.large
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Kirigami.Heading { level: 4; text: deviceData.name || "" }
                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Rectangle {
                        visible: deviceData.state === "connected"
                        width: 8; height: 8; radius: 4
                        color: Kirigami.Theme.positiveTextColor
                    }
                    Controls.Label {
                        opacity: 0.75
                        text: {
                            switch (deviceData.state) {
                                case "available": return "Available"
                                case "pairingOutgoing": return "Pairing…"
                                case "pairingIncoming": return "Wants to pair"
                                case "connected": return "Connected"
                                case "disconnected": return "Paired · Disconnected"
                                case "unreachable": return "Unreachable"
                                default: return deviceData.state || ""
                            }
                        }
                    }
                    Controls.Label {
                        opacity: 0.75
                        visible: !!(deviceData.battery)
                        text: deviceData.battery ? ("· Battery " + deviceData.battery.charge + "%" + (deviceData.battery.isCharging ? " (charging)" : "")) : ""
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            // Unpaired, currently visible on the network
            Controls.Button {
                visible: deviceData.state === "available"
                text: "Pair"
                highlighted: true
                onClicked: card.pairRequested()
            }
            Controls.Label {
                visible: deviceData.state === "pairingOutgoing"
                opacity: 0.75
                text: "Approve on your phone…"
            }
            Controls.Button {
                visible: deviceData.state === "pairingIncoming"
                text: "Accept"
                highlighted: true
                onClicked: card.acceptRequested()
            }
            Controls.Button {
                visible: deviceData.state === "pairingIncoming"
                text: "Reject"
                onClicked: card.rejectRequested()
            }

            Item { Layout.fillWidth: true }

            // Paired and reachable -- quick actions right from the card
            Controls.Button {
                visible: deviceData.state === "connected"
                text: "Send File"
                icon.name: "document-send"
                onClicked: card.sendFileRequested()
            }
            Controls.Button {
                visible: deviceData.isPaired
                text: "Open Device"
                icon.name: "arrow-right"
                onClicked: card.openRequested()
            }
        }
    }
}
