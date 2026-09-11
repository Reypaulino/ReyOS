import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Distrobox"
    width: 900
    height: 620
    minimumWidth: 700
    minimumHeight: 480

    Connections {
        target: backend
        function onActionFinished(ok, msg) {
            toast.text = msg
            toast.color = ok ? ReyOSStyle.good : ReyOSStyle.bad
            toast.open()
        }
        function onExportListReady(apps, boxName) {
            exportDialog.boxName = boxName
            exportDialog.apps = apps
            exportDialog.open()
        }
    }

    Kirigami.OverlaySheet {
        id: createSheet
        parent: appWindow.overlay
        title: "New Container"

        ColumnLayout {
            width: Kirigami.Units.gridUnit * 22
            spacing: Kirigami.Units.largeSpacing

            Controls.Label { text: "Name"; font.bold: true }
            Controls.TextField {
                id: nameField
                Layout.fillWidth: true
                placeholderText: "e.g. ubuntu-dev"
            }

            Controls.Label { text: "Base distro"; font.bold: true }
            Controls.ComboBox {
                id: imageBox
                Layout.fillWidth: true
                model: baseImages
                currentIndex: 0
                textRole: "label"
                valueRole: "image"
            }

            Controls.Button {
                Layout.alignment: Qt.AlignRight
                text: "Create"
                enabled: nameField.text.trim().length > 0
                onClicked: {
                    backend.createBox(nameField.text, imageBox.currentValue)
                    createSheet.close()
                    nameField.text = ""
                }
            }
        }
    }

    Kirigami.OverlaySheet {
        id: exportDialog
        parent: appWindow.overlay
        title: "Export an app from " + boxName
        property string boxName: ""
        property var apps: []

        ColumnLayout {
            width: Kirigami.Units.gridUnit * 22
            spacing: Kirigami.Units.smallSpacing

            Controls.Label {
                visible: exportDialog.apps.length === 0
                text: "No exportable applications found in this container."
                color: ReyOSStyle.subtext
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Repeater {
                model: exportDialog.apps
                delegate: Controls.ItemDelegate {
                    Layout.fillWidth: true
                    text: modelData.label
                    onClicked: {
                        backend.exportApp(exportDialog.boxName, modelData.id)
                        exportDialog.close()
                    }
                }
            }
        }
    }

    Kirigami.InlineMessage {
        id: toast
        parent: appWindow.overlay
        anchors {
            bottom: parent.bottom
            horizontalCenter: parent.horizontalCenter
            bottomMargin: Kirigami.Units.largeSpacing
        }
        width: Math.min(parent.width - Kirigami.Units.largeSpacing * 2, Kirigami.Units.gridUnit * 24)
        showCloseButton: true
        type: Kirigami.MessageType.Information
        function open() { visible = true; hideTimer.restart() }
        Timer { id: hideTimer; interval: 4000; onTriggered: toast.visible = false }
    }

    pageStack.initialPage: Kirigami.Page {
        title: "Containers"

        actions: [
            Kirigami.Action {
                text: "Refresh"
                icon.name: "view-refresh"
                onTriggered: backend.refreshBoxes()
            },
            Kirigami.Action {
                text: "New Container"
                icon.name: "list-add"
                onTriggered: createSheet.open()
            }
        ]

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Kirigami.InlineMessage {
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.largeSpacing
                visible: !backend.podmanReady()
                type: Kirigami.MessageType.Warning
                text: "podman isn't responding -- distrobox containers won't work until it's set up correctly."
            }

            Kirigami.Card {
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.largeSpacing
                visible: boxList.count === 0
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "package-x-generic"; Layout.preferredWidth: 48; Layout.preferredHeight: 48; Layout.alignment: Qt.AlignHCenter }
                    Controls.Label {
                        text: "No containers yet. Create one to run apps from another Linux distro right alongside ReyOS."
                        color: ReyOSStyle.subtext
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }

            Controls.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: boxList.count > 0
                ListView {
                    id: boxList
                    model: backend.boxes()
                    spacing: Kirigami.Units.smallSpacing
                    Connections {
                        target: backend
                        function onBoxesChanged() { boxList.model = backend.boxes() }
                    }

                    delegate: Kirigami.Card {
                        width: boxList.width - Kirigami.Units.largeSpacing * 2
                        anchors.horizontalCenter: parent.horizontalCenter

                        contentItem: RowLayout {
                            spacing: Kirigami.Units.largeSpacing

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                RowLayout {
                                    spacing: Kirigami.Units.smallSpacing
                                    Controls.Label { text: modelData.name; font.bold: true; font.pixelSize: 16 }
                                    Rectangle {
                                        radius: 4
                                        color: modelData.running ? ReyOSStyle.good : ReyOSStyle.subtext
                                        implicitWidth: statusLabel.implicitWidth + 12
                                        implicitHeight: statusLabel.implicitHeight + 4
                                        Controls.Label {
                                            id: statusLabel
                                            anchors.centerIn: parent
                                            text: modelData.status
                                            color: "#15110E"
                                            font.pixelSize: 11
                                        }
                                    }
                                }
                                Controls.Label { text: modelData.image; color: ReyOSStyle.subtext; font.pixelSize: 12 }
                            }

                            Controls.Button {
                                text: "Enter"
                                icon.name: "utilities-terminal"
                                onClicked: backend.enterBox(modelData.name)
                            }
                            Controls.Button {
                                text: "Export App..."
                                icon.name: "export-symbolic"
                                onClicked: backend.listExportableApps(modelData.name)
                            }
                            Controls.Button {
                                text: "Stop"
                                visible: modelData.running
                                onClicked: backend.stopBox(modelData.name)
                            }
                            Controls.Button {
                                text: "Delete"
                                icon.name: "edit-delete"
                                onClicked: backend.deleteBox(modelData.name)
                            }
                        }
                    }
                }
            }
        }
    }
}
