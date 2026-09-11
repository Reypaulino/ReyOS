import QtQuick
import QtQuick.Controls as Controls

Controls.Page {
    id: root
    // Real Kirigami.Page/ScrollablePage `actions` rendered into the shell's
    // global toolbar; this app's ApplicationWindow shim reads it directly
    // off the StackView's currentItem instead.
    property list<QtObject> actions: []

    contentItem: Controls.ScrollView {
        clip: true
        contentWidth: availableWidth

        Column {
            id: col
            width: parent.width
        }
    }

    default property alias content: col.data
}
