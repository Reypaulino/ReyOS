import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Shortcuts"
    width: 720
    height: 640
    minimumWidth: 480
    minimumHeight: 360

    // Qt.Popup made the window auto-dismiss instantly on this compositor
    // (confirmed live: process exited within 3s of launch, no crash logged)
    // -- a plain window that just opens centered is the reliable version;
    // popup-style auto-dismiss can be revisited once this is confirmed
    // working end to end.
    color: ReyOSStyle.bg

    Component.onCompleted: {
        x = Screen.width / 2 - width / 2
        y = Screen.height / 2 - height / 2
        model.entries = backend.shortcuts()
        searchField.forceActiveFocus()
    }

    Shortcut {
        sequence: "Escape"
        onActivated: appWindow.close()
    }

    QtObject {
        id: model
        property var entries: []
    }

    Rectangle {
        anchors.fill: parent
        color: ReyOSStyle.bg
        border.color: ReyOSStyle.accent
        border.width: 1
        radius: 10

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading {
                    text: "Keyboard Shortcuts"
                    level: 2
                    color: ReyOSStyle.text
                    Layout.fillWidth: true
                }
                Controls.Label {
                    text: model.entries.length + " bound"
                    color: ReyOSStyle.subtext
                }
            }

            Controls.TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Filter shortcuts…"
            }

            Controls.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true

                ListView {
                    id: shortcutList
                    model: filtered()
                    spacing: 2
                    clip: true

                    function filtered() {
                        const needle = searchField.text.toLowerCase()
                        if (!needle) return model.entries
                        return model.entries.filter(function (e) {
                            return e.action.toLowerCase().includes(needle)
                                || e.keys.toLowerCase().includes(needle)
                                || e.group.toLowerCase().includes(needle)
                        })
                    }

                    delegate: Rectangle {
                        width: shortcutList.width
                        height: row.implicitHeight + 10
                        color: index % 2 === 0 ? "transparent" : ReyOSStyle.surface
                        radius: 6

                        RowLayout {
                            id: row
                            anchors.fill: parent
                            anchors.margins: 6
                            spacing: Kirigami.Units.largeSpacing

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Controls.Label {
                                    text: modelData.action
                                    color: ReyOSStyle.text
                                }
                                Controls.Label {
                                    text: modelData.group
                                    color: ReyOSStyle.subtext
                                    font.pixelSize: Kirigami.Units.gridUnit * 0.6
                                }
                            }

                            Rectangle {
                                color: ReyOSStyle.accent
                                radius: 4
                                implicitWidth: keysLabel.implicitWidth + 14
                                implicitHeight: keysLabel.implicitHeight + 6

                                Controls.Label {
                                    id: keysLabel
                                    anchors.centerIn: parent
                                    text: modelData.keys
                                    color: "#15110E"
                                    font.bold: true
                                }
                            }
                        }
                    }

                    Controls.Label {
                        anchors.centerIn: parent
                        visible: shortcutList.count === 0
                        text: "No shortcuts match."
                        color: ReyOSStyle.subtext
                    }
                }
            }
        }
    }
}
