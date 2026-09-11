import QtQuick
import QtQuick.Controls as Controls

Controls.Label {
    id: root
    signal clicked()
    color: "#6BA5E0"
    font.underline: hover.containsMouse

    MouseArea {
        id: hover
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
