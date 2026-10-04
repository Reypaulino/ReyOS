import QtQuick
import QtQuick.Controls

AbstractButton {
    id: tile
    property var theme
    property string title: ""
    property string url: ""
    property bool isAddTile: false

    signal editRequested()
    signal removeRequested()

    implicitWidth: 112
    implicitHeight: 104
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    Accessible.name: isAddTile ? "Add shortcut" : title

    readonly property string letter: {
        var t = (title || url.replace(/^https?:\/\/(www\.)?/, "")).trim()
        return t.length ? t.charAt(0).toUpperCase() : "?"
    }

    background: Rectangle {
        radius: 14
        color: tile.hovered ? theme.hover : Qt.rgba(theme.raised.r, theme.raised.g, theme.raised.b, 0.72)
        border.width: 1
        border.color: tile.hovered ? Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.55)
                                   : Qt.rgba(theme.border.r, theme.border.g, theme.border.b, 0.45)
    }

    contentItem: Item {
        Rectangle {
            id: badge
            width: 44
            height: 44
            radius: 22
            anchors.horizontalCenter: parent.horizontalCenter
            y: 14
            color: tile.isAddTile ? "transparent" : Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.16)
            border.width: tile.isAddTile ? 0 : 1
            border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.4)

            Label {
                anchors.centerIn: parent
                visible: !tile.isAddTile
                text: tile.letter
                color: theme.glow
                font.pixelSize: 20
                font.bold: true
            }
            Image {
                anchors.centerIn: parent
                visible: tile.isAddTile
                source: Qt.resolvedUrl("../../icons/reyos-plus.svg")
                sourceSize.width: 28
                sourceSize.height: 28
                opacity: 0.8
            }
        }
        Label {
            anchors.top: badge.bottom
            anchors.topMargin: 10
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            horizontalAlignment: Text.AlignHCenter
            text: tile.isAddTile ? "Add Shortcut" : tile.title
            color: "#FFF3E6"
            font.pixelSize: 13
            elide: Text.ElideRight
        }
        ToolButton {
            id: moreButton
            visible: !tile.isAddTile && (tile.hovered || hovered || tileMenu.visible)
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 4
            width: 24
            height: 24
            padding: 0
            focusPolicy: Qt.NoFocus
            icon.source: Qt.resolvedUrl("../../icons/reyos-more.svg")
            icon.width: 14
            icon.height: 14
            background: Rectangle { radius: 6; color: moreButton.hovered ? theme.hoverStrong : "transparent" }
            onClicked: tileMenu.popup(moreButton, 0, moreButton.height)
            ToolTip.visible: hovered
            ToolTip.text: "Edit or remove"
            Accessible.name: "Edit or remove " + tile.title
        }
    }

    TapHandler {
        acceptedButtons: Qt.RightButton
        enabled: !tile.isAddTile
        onTapped: function(eventPoint) { tileMenu.popup() }
    }

    ToolTip.visible: hovered && !tile.isAddTile && !moreButton.hovered && !tileMenu.visible
    ToolTip.delay: 700
    ToolTip.text: tile.url

    Menu {
        id: tileMenu
        background: Rectangle {
            implicitWidth: 170
            color: theme.raised
            border.color: theme.border
            border.width: 1
            radius: 10
        }
        MenuItem { text: "Edit shortcut"; onTriggered: tile.editRequested() }
        MenuItem { text: "Remove"; onTriggered: tile.removeRequested() }
    }
}
