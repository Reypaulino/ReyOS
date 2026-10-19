import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// One card style for every page. `accented` draws the Look's accent along the left edge.
Kirigami.AbstractCard {
    id: card
    property bool accented: false

    Layout.fillWidth: true
    padding: Kirigami.Units.gridUnit
    Kirigami.Theme.colorSet: Kirigami.Theme.View
    Kirigami.Theme.inherit: false

    background: Rectangle {
        radius: Kirigami.Units.gridUnit * 0.6
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: card.accented
            ? Qt.rgba(Kirigami.Theme.highlightColor.r, Kirigami.Theme.highlightColor.g, Kirigami.Theme.highlightColor.b, 0.6)
            : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.12)

        Rectangle {
            visible: card.accented
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; margins: 1 }
            width: 4
            radius: 2
            color: Kirigami.Theme.highlightColor
        }
    }
}
