import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls

// Kirigami.ApplicationWindow, reduced to what this app actually uses: a
// docked (non-modal, non-collapsible) globalDrawer sidebar next to a page
// stack, plus a simple top toolbar showing the current page's title and
// actions (Kirigami normally renders these via pageStack.globalToolBar,
// which has no QtQuick Controls equivalent -- this replaces it directly).
Controls.ApplicationWindow {
    id: root
    // Kirigami.ApplicationWindow defaults to visible; plain Controls
    // .ApplicationWindow does not, and Main.qml never sets it explicitly
    // (it never had to against the real Kirigami type).
    visible: true
    property Item globalDrawer
    readonly property alias pageStack: stack

    onGlobalDrawerChanged: {
        if (globalDrawer) {
            // Anchoring width too (anchors.fill) would overwrite the
            // drawer's own explicit `width: ...` with a binding back onto
            // sidebarSlot -- whose own width is itself derived *from*
            // globalDrawer.width below, a direct circular binding that
            // collapsed both to 0 (confirmed live via QQmlProperty
            // inspection). Only height/position need to track the slot;
            // width stays whatever the drawer itself declared.
            globalDrawer.parent = sidebarSlot
            globalDrawer.anchors.top = sidebarSlot.top
            globalDrawer.anchors.bottom = sidebarSlot.bottom
            globalDrawer.anchors.left = sidebarSlot.left
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Item {
            id: sidebarSlot
            Layout.fillHeight: true
            Layout.preferredWidth: (root.globalDrawer && root.globalDrawer.visible) ? root.globalDrawer.width : 0
            clip: true
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Controls.ToolBar {
                Layout.fillWidth: true
                visible: stack.depth > 1

                RowLayout {
                    anchors.fill: parent
                    Controls.ToolButton {
                        icon.name: "go-previous"
                        text: "Back"
                        onClicked: stack.pop()
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: stack.currentItem && stack.currentItem.title ? stack.currentItem.title : ""
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Repeater {
                        model: stack.currentItem && stack.currentItem.actions ? stack.currentItem.actions : []
                        delegate: Controls.ToolButton {
                            required property var modelData
                            action: modelData
                            display: Controls.ToolButton.IconOnly
                        }
                    }
                }
            }

            Controls.StackView {
                id: stack
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }
    }
}
