pragma Singleton
import QtQuick
import "../" as Reader

// Kirigami's real Theme.colorSet is an attached property used to switch
// between the app's Window/View/Button/etc. palettes. This app only ever
// reads backgroundColor/smallFont, and only ever *set* colorSet as a
// cosmetic hint -- so every `Kirigami.Theme.colorSet: Kirigami.Theme.View`
// assignment site was dropped in the QtQuick Controls rewrite, and no
// colorSet-like property exists here.
QtObject {
    readonly property color backgroundColor: Reader.ReyOSStyle.bg
    readonly property color textColor: Reader.ReyOSStyle.text

    readonly property QtObject smallFont: QtObject {
        readonly property int pointSize: 9
    }
}
