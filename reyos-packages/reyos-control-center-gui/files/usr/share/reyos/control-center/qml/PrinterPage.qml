import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: printerPage
    title: "Printers · Scanners"

    property bool busy: false
    property var printers: []
    property var discoveredDevices: []
    property var scanners: []
    property bool discovering: false
    property bool scanningDevices: false
    property bool hasSearchedPrinters: false

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: { backend.refreshPrinters(); backend.refreshScanners() }
        }
    ]

    Component.onCompleted: {
        backend.refreshPrinters()
        backend.refreshScanners()
    }

    Connections {
        target: backend
        function onPrintersListed(list) { printers = list }
        function onPrinterDevicesFound(list) { discoveredDevices = list; discovering = false; hasSearchedPrinters = true }
        function onScannersListed(list) { scanners = list; scanningDevices = false }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) { backend.refreshPrinters(); backend.refreshScanners() }
        }
    }

    Kirigami.OverlaySheet {
        id: addSheet
        parent: applicationWindow().overlay
        title: "Add Printer"
        property string uri: ""

        ColumnLayout {
            width: Kirigami.Units.gridUnit * 22
            spacing: Kirigami.Units.largeSpacing

            Controls.Label { text: addSheet.uri; color: Kirigami.Theme.disabledTextColor; wrapMode: Text.Wrap; Layout.fillWidth: true }

            Controls.Label { text: "Name"; font.bold: true }
            Controls.TextField {
                id: printerNameField
                Layout.fillWidth: true
                placeholderText: "e.g. Office-Printer"
            }

            Controls.Button {
                Layout.alignment: Qt.AlignRight
                text: "Add"
                enabled: printerNameField.text.trim().length > 0
                onClicked: {
                    backend.addPrinter(printerNameField.text, addSheet.uri)
                    addSheet.close()
                    printerNameField.text = ""
                }
            }
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: "Set up printers and scanners without hunting for drivers -- most printers made since ~2015 work out of the box."
        }

        // -- Configured printers ------------------------------------------
        Kirigami.Heading { text: "Printers"; level: 3 }

        Controls.Label {
            visible: printers.length === 0
            text: "No printers configured yet."
            opacity: 0.7
        }

        Repeater {
            model: printers
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon { source: "printer"; Layout.preferredWidth: Kirigami.Units.iconSizes.medium; Layout.preferredHeight: Kirigami.Units.iconSizes.medium }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Label { text: modelData.name; font.bold: true }
                            Kirigami.Icon {
                                source: "emblem-favorite"
                                visible: modelData.isDefault
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                            }
                        }
                        Controls.Label { text: modelData.status; opacity: 0.7 }
                    }
                    Controls.Button {
                        text: "Set Default"
                        visible: !modelData.isDefault
                        enabled: !busy
                        onClicked: { busy = true; backend.setDefaultPrinter(modelData.name) }
                    }
                    Controls.Button {
                        text: "Test Print"
                        enabled: !busy
                        onClicked: { busy = true; backend.testPrint(modelData.name) }
                    }
                    Controls.Button {
                        text: "Remove"
                        enabled: !busy
                        onClicked: { busy = true; backend.removePrinter(modelData.name) }
                    }
                }
            }
        }

        RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Controls.Button {
                text: discovering ? "Searching..." : "Find Printers"
                enabled: !discovering
                onClicked: { discovering = true; discoveredDevices = []; backend.discoverPrinterDevices() }
            }
            Controls.BusyIndicator { visible: discovering; Layout.preferredWidth: Kirigami.Units.iconSizes.small; Layout.preferredHeight: Kirigami.Units.iconSizes.small }
        }

        Controls.Label {
            visible: !discovering && hasSearchedPrinters && discoveredDevices.length === 0
            text: "No new printers found on the network or USB."
            opacity: 0.7
        }

        Repeater {
            model: discoveredDevices
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Controls.Label { text: modelData.uri; font.bold: true; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        Controls.Label { text: modelData.kind; opacity: 0.7 }
                    }
                    Controls.Button {
                        text: "Add..."
                        onClicked: {
                            addSheet.uri = modelData.uri
                            addSheet.open()
                        }
                    }
                }
            }
        }

        Kirigami.Separator { Layout.fillWidth: true }

        // -- Scanners -------------------------------------------------------
        Kirigami.Heading { text: "Scanners"; level: 3 }

        Controls.Label {
            visible: scanners.length === 0 && !scanningDevices
            text: "No scanners detected."
            opacity: 0.7
        }

        Controls.BusyIndicator {
            visible: scanningDevices
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Kirigami.Units.iconSizes.small
        }

        Repeater {
            model: scanners
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon { source: "scanner"; Layout.preferredWidth: Kirigami.Units.iconSizes.medium; Layout.preferredHeight: Kirigami.Units.iconSizes.medium }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Controls.Label { text: modelData.label; font.bold: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        Controls.Label { text: modelData.device; opacity: 0.7; elide: Text.ElideMiddle; Layout.fillWidth: true }
                    }
                    Controls.Button {
                        text: "Scan Test Page"
                        enabled: !busy
                        onClicked: { busy = true; backend.scanTestPage(modelData.device) }
                    }
                }
            }
        }

        Controls.Button {
            text: "Detect Scanners"
            enabled: !scanningDevices
            onClicked: { scanningDevices = true; backend.refreshScanners() }
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        Item { Layout.fillWidth: true; Layout.preferredHeight: Kirigami.Units.gridUnit * 3 }
    }
}
