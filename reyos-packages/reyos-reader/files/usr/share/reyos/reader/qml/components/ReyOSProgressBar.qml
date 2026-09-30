import QtQuick
import "../kirishim" as Kirigami
import "../" as Reader

// Drop-in replacement for QtQuick.Controls' ProgressBar (from/to/value/
// indeterminate). Under the KDE desktop style, Controls.ProgressBar keeps the
// whole window repainting nonstop -- even when it's hidden and not
// indeterminate. Measured live on ReyOS-Test (2026-09-29): Control Center's
// Appearance page idled at ~190% CPU (+ ~110% in KWin) with its one hidden
// progress bar, 0% with it removed. Two plain Rectangles have no such cost;
// the indeterminate slide only animates while it's actually on screen.
// Reader's copy uses its own kirishim stand-in + ReyOSStyle instead of
// org.kde.kirigami, which isn't installed on Ubuntu (the .deb target) --
// importing it broke the library cards there ("module org.kde.kirigami is
// not installed"). Fill uses the Look accent via ReyOSStyle.accent.
Item {
    id: root

    property real from: 0
    property real to: 1
    property real value: 0
    property bool indeterminate: false
    readonly property real position: to > from ? Math.max(0, Math.min(1, (value - from) / (to - from))) : 0

    implicitWidth: Kirigami.Units.gridUnit * 10
    implicitHeight: Math.round(Kirigami.Units.smallSpacing * 1.5)
    clip: true

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Qt.rgba(Reader.ReyOSStyle.text.r, Reader.ReyOSStyle.text.g, Reader.ReyOSStyle.text.b, 0.15)
    }

    Rectangle {
        visible: !root.indeterminate
        width: parent.width * root.position
        height: parent.height
        radius: height / 2
        color: Reader.ReyOSStyle.accent
    }

    Rectangle {
        id: slider
        visible: root.indeterminate
        width: parent.width * 0.3
        height: parent.height
        radius: height / 2
        color: Reader.ReyOSStyle.accent

        NumberAnimation on x {
            running: root.indeterminate && root.visible
            from: -slider.width
            to: root.width
            duration: 1400
            loops: Animation.Infinite
        }
    }
}
