import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    title: ""
    padding: 0

    property var selectedApps: []
    property bool done: false
    property string resultMessage: ""

    Connections {
        target: backend
        function onProgressLine(line) {
            logArea.append(line)
        }
        function onInstallFinished(ok, message) {
            done = true
            resultMessage = message
            applicationWindow().pageStack.push(Qt.resolvedUrl("DonePage.qml"), { resultMessage: message, success: ok })
        }
    }

    Component.onCompleted: {
        if (selectedApps.length === 0) {
            applicationWindow().pageStack.push(Qt.resolvedUrl("DonePage.qml"), { resultMessage: "Nothing to install.", success: true })
        } else {
            backend.startInstall(selectedApps.map(a => a.id))
        }
    }

    background: Rectangle { color: ReyOSStyle.bg }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing * 2
        spacing: Kirigami.Units.largeSpacing

        Controls.Label {
                text: "Installing…"
                font.pointSize: 20
                font.bold: true
                color: ReyOSStyle.text
            }

            Controls.ProgressBar {
                Layout.fillWidth: true
                indeterminate: !done
                value: done ? 1 : 0
            }

            Controls.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Controls.TextArea {
                    id: logArea
                    readOnly: true
                    wrapMode: TextEdit.Wrap
                    color: ReyOSStyle.text
                    background: Rectangle { color: Qt.darker(ReyOSStyle.bg, 1.2) }
                    font.family: "monospace"
                    font.pointSize: 9
                    function append(line) {
                        text += line + "\n"
                        cursorPosition = text.length
                    }
                }
            }
    }
}
