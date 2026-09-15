pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#15110E"
    // Falls back to the copper literal when no context property is set
    // (e.g. loaded standalone under qmlscene outside the real app).
    readonly property color accent: (typeof reyosAccentColor !== "undefined" && reyosAccentColor) ? reyosAccentColor : "#C97932"
    readonly property color text: "#FFF3E6"
    readonly property color good: "#F0B46A"
    readonly property color warn: "#E6AE66"
    readonly property color bad: "#E74C3C"
}
