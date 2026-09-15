pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#15110E"
    readonly property color surface: "#211711"
    // Falls back to the copper literal when no context property is set
    // (e.g. loaded standalone under qmlscene outside the real app).
    readonly property color accent: (typeof reyosAccentColor !== "undefined" && reyosAccentColor) ? reyosAccentColor : "#C97932"
    readonly property color text: "#FFF3E6"
    readonly property color subtext: "#D7C1AA"
    readonly property color good: "#9AD8AE"
    readonly property color warn: "#E6AE66"
    readonly property color bad: "#E74C3C"
    readonly property color border: "#8E5A2E"
}
