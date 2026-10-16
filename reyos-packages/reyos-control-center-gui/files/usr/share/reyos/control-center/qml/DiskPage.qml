import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Disk"

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    property bool loading: false

    function refresh() {
        loading = true
        backend.refreshDiskInfo()
    }

    Connections {
        target: backend
        function onDiskInfoReady(info) {
            loading = false
            fsModel.clear()
            for (var i = 0; i < info.filesystems.length; i++) fsModel.append(info.filesystems[i])
            largestModel.clear()
            for (var j = 0; j < info.largest.length; j++) largestModel.append(info.largest[j])
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: fsModel }
    ListModel { id: largestModel }

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
                Kirigami.Heading { text: "Drives"; level: 3 }
                Repeater {
                    model: fsModel
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: index > 0 ? Kirigami.Units.smallSpacing : 0
                        spacing: Kirigami.Units.smallSpacing
                        RowLayout {
                            Layout.fillWidth: true
                            // "/" and long /run/media/... paths mean little to most people.
                            Controls.Label {
                                text: mount === "/" ? "ReyOS (system)" : mount === "/boot" ? "Startup files (/boot)"
                                      : mount === "/home" ? "Your files (/home)"
                                      : mount.indexOf("/run/media/") === 0 ? "Other drive (" + mount.split("/").pop().slice(0, 8) + "…)" : mount
                                font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            Controls.Label {
                                text: (parseInt(pct) >= 90 ? "Almost full · " : "") + used + " / " + size + "  (" + pct + ")"
                                color: parseInt(pct) >= 90 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                            }
                        }
                        ReyOSProgressBar {
                            Layout.fillWidth: true
                            from: 0; to: 100
                            value: parseInt(pct)
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
                Kirigami.Heading { text: "What takes the most space in your home folder"; level: 3 }
                Repeater {
                    model: largestModel
                    delegate: RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Label { text: itemSize; Layout.preferredWidth: 70; font.family: "monospace" }
                        Controls.Label { text: itemPath.replace(/^\/home\/[^\/]+/, "~"); elide: Text.ElideMiddle; Layout.fillWidth: true }
                    }
                }
            }
        }
    }
}
