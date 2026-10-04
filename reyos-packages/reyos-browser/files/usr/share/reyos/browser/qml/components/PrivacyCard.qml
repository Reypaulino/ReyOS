import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: card
    property var theme
    property url iconSource
    property string title: ""
    property string body: ""
    property bool divider: false

    implicitHeight: row.implicitHeight + 32
    Layout.fillWidth: true
    Layout.fillHeight: true
    Layout.alignment: Qt.AlignTop

    Rectangle {
        visible: card.divider
        width: 1
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.topMargin: 16
        anchors.bottomMargin: 16
        color: Qt.rgba(card.theme.border.r, card.theme.border.g, card.theme.border.b, 0.5)
    }

    RowLayout {
        id: row
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 16
        spacing: 14

        Rectangle {
            Layout.alignment: Qt.AlignTop
            implicitWidth: 40
            implicitHeight: 40
            radius: 20
            color: Qt.rgba(card.theme.accent.r, card.theme.accent.g, card.theme.accent.b, 0.14)
            ToolButton {
                anchors.centerIn: parent
                hoverEnabled: false
                focusPolicy: Qt.NoFocus
                Accessible.ignored: true
                padding: 0
                background: null
                icon.source: card.iconSource
                icon.width: 20
                icon.height: 20
                icon.color: card.theme.glow
                opacity: 1.0
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            spacing: 4
            Label {
                text: card.title
                color: "#FFF3E6"
                font.pixelSize: 15
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
            Label {
                text: card.body
                color: "#BBA896"
                font.pixelSize: 13
                lineHeight: 1.15
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }
        }
    }
}
