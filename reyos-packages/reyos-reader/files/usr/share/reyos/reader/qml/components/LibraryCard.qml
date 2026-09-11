import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "../kirishim" as Kirigami
import "../" as Reader

Rectangle {
    id: card
    property var item
    signal open()
    signal toggleFavorite()
    signal remove()

    Layout.preferredWidth: 170
    Layout.preferredHeight: 260
    color: Kirigami.Theme.backgroundColor
    border.color: Qt.rgba(0, 0, 0, 0.25)
    border.width: 1
    radius: 8
    opacity: item.missing ? 0.5 : 1.0

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 170
            Image {
                anchors.fill: parent
                fillMode: Image.PreserveAspectCrop
                source: item.cover_cache_path ? ("file://" + item.cover_cache_path) : ""
                visible: item.cover_cache_path
                asynchronous: true
            }
            Rectangle {
                anchors.fill: parent
                visible: !item.cover_cache_path
                color: Reader.ReyOSStyle.bg
                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: 48
                    height: 48
                    source: item.format === "pdf" ? "application-pdf" : "x-office-document"
                }
            }
            Controls.ToolButton {
                anchors.top: parent.top
                anchors.right: parent.right
                icon.name: item.favorite ? "starred-symbolic" : "non-starred-symbolic"
                icon.color: "white"
                background: Rectangle {
                    radius: width / 2
                    color: Qt.rgba(0, 0, 0, 0.45)
                }
                onClicked: card.toggleFavorite()
            }
            Controls.ToolButton {
                anchors.top: parent.top
                anchors.left: parent.left
                icon.name: "edit-delete"
                icon.color: "white"
                background: Rectangle {
                    radius: width / 2
                    color: Qt.rgba(0, 0, 0, 0.45)
                }
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Remove from library (keeps the file)"
                onClicked: card.remove()
            }
        }

        Controls.Label {
            Layout.fillWidth: true
            text: item.title
            elide: Text.ElideRight
            wrapMode: Text.NoWrap
            font.bold: true
        }
        Controls.Label {
            Layout.fillWidth: true
            visible: !!item.author
            text: item.author || ""
            elide: Text.ElideRight
            opacity: 0.7
            font.pointSize: Kirigami.Theme.smallFont.pointSize
        }
        Controls.ProgressBar {
            Layout.fillWidth: true
            visible: item.progress_percent > 0
            from: 0; to: 100
            value: item.progress_percent
        }
        Controls.Label {
            visible: item.missing
            text: "File not found"
            color: Reader.ReyOSStyle.bad
            font.pointSize: Kirigami.Theme.smallFont.pointSize
        }
    }

    MouseArea {
        anchors.fill: parent
        z: -1
        enabled: !item.missing
        onClicked: card.open()
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onPressed: if (mouse.button === Qt.RightButton) contextMenu.popup()
    }

    Controls.Menu {
        id: contextMenu
        Controls.MenuItem { text: "Open"; onTriggered: card.open() }
        Controls.MenuItem {
            text: item.favorite ? "Remove from Favorites" : "Add to Favorites"
            onTriggered: card.toggleFavorite()
        }
        Controls.MenuItem { text: "Remove from Library"; onTriggered: card.remove() }
    }
}
