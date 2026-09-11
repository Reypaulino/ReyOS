import QtQuick
import QtQuick.Layouts

// Kirigami.GlobalDrawer, docked (modal: false, collapsible: false) mode
// only -- the only mode this app actually uses. ApplicationWindow's shim
// lays this out as a permanent sidebar next to the page StackView.
Item {
    id: root
    property bool modal: false
    property bool collapsible: false
    property Item header
    default property alias content: contentArea.data

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            id: headerSlot
            Layout.fillWidth: true
            implicitHeight: root.header ? root.header.implicitHeight : 0
        }

        Item {
            id: contentArea
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }

    Component.onCompleted: {
        if (root.header) {
            root.header.parent = headerSlot
            root.header.anchors.fill = headerSlot
        }
        // The default-property content (declared expecting a real Layout
        // parent, e.g. `Layout.fillWidth/fillHeight`) actually lands inside
        // a plain Item here, where those attached properties are no-ops --
        // anchor it directly instead so it still fills the content area.
        for (var i = 0; i < contentArea.children.length; i++) {
            contentArea.children[i].anchors.fill = contentArea
        }
    }
}
