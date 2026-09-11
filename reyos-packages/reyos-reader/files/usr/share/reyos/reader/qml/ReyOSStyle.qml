pragma Singleton
import QtQuick

QtObject {
    readonly property color bg: "#15110E"
    readonly property color accent: "#C97932"
    readonly property color text: "#FFF3E6"
    readonly property color good: "#F0B46A"
    readonly property color warn: "#E6AE66"
    readonly property color bad: "#E74C3C"

    // Reading-content themes -- independent of the desktop's active
    // Kirigami color scheme, so a book stays comfortable to read even if
    // the shell around it is using the other ReyOS theme (see docs/reader.md).
    readonly property color sepiaBg: "#F4ECD8"
    readonly property color sepiaText: "#2B2116"
    readonly property color darkReadBg: "#1B1712"
    readonly property color darkReadText: "#EDE3D6"
    readonly property color lightReadBg: "#FAF3E3"
    readonly property color lightReadText: "#3A2E22"
}
