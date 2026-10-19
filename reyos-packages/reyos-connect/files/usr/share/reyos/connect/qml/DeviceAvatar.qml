import QtQuick
import org.kde.kirigami as Kirigami

// Device icon on a soft accent-colored circle.
Rectangle {
    id: avatar
    property string iconName: "smartphone"
    property int size: Kirigami.Units.iconSizes.huge
    property bool active: true

    implicitWidth: size
    implicitHeight: size
    radius: size / 2
    color: active
        ? Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.18)
        : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.08)

    Kirigami.Icon {
        anchors.centerIn: parent
        width: Math.round(avatar.size * 0.58)
        height: width
        source: avatar.iconName || "smartphone"
        opacity: avatar.active ? 1 : 0.6
    }
}
