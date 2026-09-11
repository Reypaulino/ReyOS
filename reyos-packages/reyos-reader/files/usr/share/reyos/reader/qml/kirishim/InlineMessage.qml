import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "." as Kirigami

Rectangle {
    id: root
    property int type: Kirigami.MessageType.Information
    property alias text: label.text
    property bool showCloseButton: false

    implicitHeight: row.implicitHeight + Kirigami.Units.smallSpacing * 2
    radius: 6
    color: type === Kirigami.MessageType.Positive ? Qt.rgba(0.2, 0.6, 0.3, 0.25)
         : type === Kirigami.MessageType.Error ? Qt.rgba(0.7, 0.2, 0.2, 0.25)
         : type === Kirigami.MessageType.Warning ? Qt.rgba(0.7, 0.5, 0.1, 0.25)
         : Qt.rgba(1, 1, 1, 0.08)

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Controls.Label {
            id: label
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
        Controls.ToolButton {
            icon.name: "window-close"
            visible: root.showCloseButton
            onClicked: root.visible = false
        }
    }
}
