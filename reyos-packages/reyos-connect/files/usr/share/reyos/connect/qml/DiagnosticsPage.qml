import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Connection Diagnostics"

    property var rows: []
    property bool busy: false

    function refresh() { busy = true; backend.refreshConnectionDiagnostics() }

    Component.onCompleted: refresh()

    Connections {
        target: backend
        function onConnectionDiagnosticsReady(result) { busy = false; rows = result }
    }

    actions: [
        Kirigami.Action { text: "Close"; icon.name: "window-close"; onTriggered: applicationWindow().pageStack.pop() },
        Kirigami.Action { text: "Menu"; icon.name: "application-menu"; onTriggered: applicationWindow().globalDrawer.open() },
        Kirigami.Action { text: "Refresh"; icon.name: "view-refresh"; onTriggered: refresh() }
    ]

    function resultColor(result) {
        if (result === "PASS") return Kirigami.Theme.positiveTextColor
        if (result === "FAIL") return Kirigami.Theme.negativeTextColor
        return Kirigami.Theme.disabledTextColor
    }

    ColumnLayout {
        width: parent.width
        spacing: Kirigami.Units.largeSpacing

        Controls.ProgressBar { Layout.fillWidth: true; indeterminate: true; visible: busy }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Repeater {
                    model: rows
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            Controls.Label { text: modelData.check; font.bold: true; Layout.preferredWidth: Kirigami.Units.gridUnit * 8 }
                            Controls.Label {
                                text: modelData.result.replace("_", " ")
                                color: resultColor(modelData.result)
                                font.bold: true
                            }
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: Kirigami.Units.smallSpacing
                            wrapMode: Text.Wrap
                            opacity: 0.7
                            font.pointSize: 9
                            text: modelData.detail
                        }
                        Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }
                    }
                }
                Controls.Label {
                    visible: rows.length === 0 && !busy
                    opacity: 0.6
                    text: "No diagnostics yet -- click Refresh."
                }
            }
        }
    }
}
