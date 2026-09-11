import QtQuick.Controls as Controls

Controls.TextField {
    leftPadding: 32
    Controls.ToolButton {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        icon.name: "edit-find"
        flat: true
        enabled: false
    }
}
