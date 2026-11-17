import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One row of the New Tab dashboard / tab search: an open tab, a web app, a
// bookmark or "Search the web". Pure display; the owner decides what a click
// or Enter does.
ItemDelegate {
    id: row
    property var theme
    property string kind: ""          // "tab" | "app" | "bookmark" | "web"
    property string title: ""
    property string detail: ""
    property string iconUrl: ""
    property string sleepState: ""    // tab lifecycle: "", "frozen", "discarded"
    property bool alreadyOpen: false  // bookmark that is also an open tab
    property bool current: false      // keyboard highlight

    implicitHeight: 52
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    padding: 0
    Accessible.name: actionText + ": " + title
    Accessible.role: Accessible.ListItem

    readonly property string actionText: kind === "tab" ? "Switch to tab"
                                       : kind === "app" ? "Open app"
                                       : kind === "bookmark" ? (alreadyOpen ? "Bookmark · open in a tab" : "Bookmark")
                                       : "Search"
    readonly property string letter: {
        var t = (title || detail).replace(/^https?:\/\/(www\.)?/, "").trim()
        return t.length ? t.charAt(0).toUpperCase() : "?"
    }

    background: Rectangle {
        radius: 10
        color: row.current ? theme.hover : (row.hovered ? Qt.rgba(theme.hover.r, theme.hover.g, theme.hover.b, 0.6) : "transparent")
        border.width: row.current ? 1 : 0
        border.color: Qt.rgba(theme.accent.r, theme.accent.g, theme.accent.b, 0.55)
    }

    contentItem: RowLayout {
        spacing: 12
        Item { Layout.preferredWidth: 4 }
        Rectangle {
            Layout.preferredWidth: 32
            Layout.preferredHeight: 32
            radius: 9
            color: theme.base
            border.color: Qt.rgba(theme.border.r, theme.border.g, theme.border.b, 0.7)
            Image {
                id: rowIcon
                anchors.centerIn: parent
                visible: status === Image.Ready
                source: row.kind === "web" ? Qt.resolvedUrl("../../icons/reyos-search.svg")
                      : (row.kind === "app" && row.iconUrl.length ? row.iconUrl : "")
                sourceSize.width: row.kind === "web" ? 18 : 24
                sourceSize.height: row.kind === "web" ? 18 : 24
                asynchronous: true
            }
            Label {
                anchors.centerIn: parent
                visible: !rowIcon.visible
                text: row.letter
                color: theme.glow
                font.bold: true
                font.pixelSize: 14
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Label {
                text: row.title
                color: "#FFF3E6"
                font.pixelSize: 14
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Label {
                visible: text.length > 0
                text: row.detail
                color: "#BBA896"
                font.pixelSize: 12
                elide: Text.ElideMiddle
                Layout.fillWidth: true
            }
        }
        Label {
            visible: row.kind === "tab" && row.sleepState.length > 0
            text: row.sleepState === "discarded" ? "Unloaded" : "Sleeping"
            color: "#F4D5A8"
            font.pixelSize: 11
            ToolTip.visible: stateHover.hovered
            ToolTip.text: row.sleepState === "discarded" ? "Unloaded to save memory: reloads when you switch to it"
                                                    : "Paused to save memory: wakes when you switch to it"
            HoverHandler { id: stateHover }
        }
        Label {
            text: row.actionText
            color: row.current || row.hovered ? theme.glow : "#9F8873"
            font.pixelSize: 12
        }
        Item { Layout.preferredWidth: 6 }
    }
}
