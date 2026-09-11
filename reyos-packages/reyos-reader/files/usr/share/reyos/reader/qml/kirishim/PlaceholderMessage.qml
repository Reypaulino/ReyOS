import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "." as Kirigami

ColumnLayout {
    id: root
    property alias text: label.text
    property string explanation: ""
    property alias icon: iconItem

    spacing: Kirigami.Units.smallSpacing

    Kirigami.Icon {
        id: iconItem
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 48
        Layout.preferredHeight: 48
        opacity: 0.6
    }
    Controls.Label {
        id: label
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        horizontalAlignment: Text.AlignHCenter
        font.bold: true
        opacity: 0.8
    }
    Controls.Label {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignHCenter
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: root.explanation
        visible: root.explanation.length > 0
        opacity: 0.6
    }
}
