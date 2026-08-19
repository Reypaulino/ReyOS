import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    title: ""
    padding: 0

    property string resultMessage: "All done!"
    property bool success: true

    background: Rectangle { color: ReyOSStyle.bg }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: Kirigami.Units.largeSpacing * 2
        width: parent.width * 0.7

        Kirigami.Icon {
                source: success ? "checkmark" : "dialog-warning"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 64
                Layout.preferredHeight: 64
            }

            Controls.Label {
                text: success ? "You're all set!" : "Something went wrong"
                font.pointSize: 20
                font.bold: true
                color: ReyOSStyle.text
                Layout.alignment: Qt.AlignHCenter
            }

            Controls.Label {
                text: resultMessage
                color: ReyOSStyle.text
                opacity: 0.8
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Layout.alignment: Qt.AlignHCenter
                Layout.fillWidth: true
            }

            RowLayout {
                spacing: Kirigami.Units.largeSpacing
                Layout.alignment: Qt.AlignHCenter

                Controls.Button {
                    text: "Check for Updates"
                    icon.name: "system-software-update"
                    onClicked: {
                        backend.openControlCenterUpdates()
                        Qt.quit()
                    }
                }

                Controls.Button {
                    text: "Finish"
                    highlighted: true
                    onClicked: Qt.quit()
                }
            }
    }
}
