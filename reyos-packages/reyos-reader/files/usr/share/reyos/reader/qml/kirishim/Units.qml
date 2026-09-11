pragma Singleton
import QtQuick

QtObject {
    readonly property int smallSpacing: 6
    readonly property int largeSpacing: 12
    readonly property int gridUnit: 18

    readonly property QtObject iconSizes: QtObject {
        readonly property int small: 16
        readonly property int medium: 32
    }
}
