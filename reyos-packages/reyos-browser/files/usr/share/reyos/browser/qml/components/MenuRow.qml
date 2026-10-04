import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ItemDelegate {
    id: row
    property url iconSource
    property string shortcutText: ""
    property bool toggle: false
    property bool on: false
    property color hoverColor: "#3B2B1C"
    property color accent: "#C97932"

    Layout.fillWidth: true
    implicitHeight: 36
    leftPadding: 10
    rightPadding: 10
    focusPolicy: Qt.NoFocus
    opacity: enabled ? 1.0 : 0.45

    background: Rectangle {
        radius: 7
        color: row.hovered && row.enabled ? row.hoverColor : "transparent"
    }

    contentItem: RowLayout {
        spacing: 12
        Image {
            source: row.iconSource
            visible: row.iconSource.toString().length > 0
            sourceSize.width: 18
            sourceSize.height: 18
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
        }
        Label {
            text: row.text
            color: "#FFF3E6"
            font.pixelSize: 14
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Label {
            visible: row.shortcutText.length > 0
            text: row.shortcutText
            color: "#9F8873"
            font.pixelSize: 12
        }
        Rectangle {
            visible: row.toggle
            implicitWidth: 30
            implicitHeight: 16
            radius: 8
            color: row.on ? row.accent : "#4A3F36"
            Rectangle {
                width: 12
                height: 12
                radius: 6
                y: 2
                x: row.on ? parent.width - width - 2 : 2
                color: "#FFF3E6"
            }
        }
    }
}
