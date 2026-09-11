import QtQuick
import QtQuick.Controls as Controls
import "../" as Reader

// A small dog-eared ribbon shown in the corner of a bookmarked page/chapter,
// Kindle-style -- a toolbar icon alone wasn't visible/obvious enough while
// actually reading (user feedback: wanted it "just like reading from a
// Kindle"). Click toggles the bookmark, same as the toolbar button.
Item {
    id: ribbon
    signal clicked()
    width: 26
    height: 38

    Canvas {
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.fillStyle = Reader.ReyOSStyle.accent
            ctx.beginPath()
            ctx.moveTo(0, 0)
            ctx.lineTo(width, 0)
            ctx.lineTo(width, height)
            ctx.lineTo(width / 2, height - 10)
            ctx.lineTo(0, height)
            ctx.closePath()
            ctx.fill()
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: ribbon.clicked()
        Controls.ToolTip.visible: containsMouse
        Controls.ToolTip.text: "Bookmarked -- click to remove"
    }
}
