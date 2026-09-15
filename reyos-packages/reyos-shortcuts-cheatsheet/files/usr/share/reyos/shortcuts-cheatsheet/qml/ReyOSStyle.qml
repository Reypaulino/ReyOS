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
}
