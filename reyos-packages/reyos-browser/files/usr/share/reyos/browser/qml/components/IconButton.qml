import QtQuick
import QtQuick.Controls

ToolButton {
    id: control
    property url iconSource
    property string tip: ""
    property color hoverColor: "#3B2B1C"
    property color tint: "transparent"
    property bool active: false
    property bool badge: false
    property color badgeColor: "#C97932"
    property int iconSize: 20

    implicitWidth: 38
    implicitHeight: 38
    focusPolicy: Qt.NoFocus
    icon.source: iconSource
    icon.width: iconSize
    icon.height: iconSize
    icon.color: tint
    opacity: enabled ? 1.0 : 0.38
    padding: 0

    background: Rectangle {
        radius: 9
        color: control.down ? Qt.darker(control.hoverColor, 1.15)
             : (control.hovered || control.active ? control.hoverColor : "transparent")
    }

    Rectangle {
        visible: control.badge
        width: 8
        height: 8
        radius: 4
        color: control.badgeColor
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 6
        anchors.rightMargin: 6
    }

    ToolTip.visible: hovered && tip.length > 0
    ToolTip.delay: 600
    ToolTip.text: tip
    Accessible.name: tip
}
