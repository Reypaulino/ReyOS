import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "kirishim" as Kirigami
import "." as Reader

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Reader"
    width: 1100
    height: 720
    minimumWidth: 900
    minimumHeight: 620

    property bool distractionFree: false

    component NavItem: Controls.ItemDelegate {
        id: navDelegate
        property bool navHighlighted: false
        Layout.fillWidth: true
        highlighted: navHighlighted
        contentItem: RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Kirigami.Icon { source: navDelegate.icon.name; Layout.preferredWidth: Kirigami.Units.iconSizes.small; Layout.preferredHeight: Kirigami.Units.iconSizes.small }
            Controls.Label { text: navDelegate.text; Layout.fillWidth: true; elide: Text.ElideRight }
        }
    }

    globalDrawer: Kirigami.GlobalDrawer {
        id: drawer
        modal: false
        collapsible: false
        width: Kirigami.Units.gridUnit * 13
        visible: !appWindow.distractionFree

        header: Item {
            implicitHeight: headerRow.implicitHeight + Kirigami.Units.largeSpacing * 2
            RowLayout {
                id: headerRow
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: "reyos-reader"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                }
                Kirigami.Heading {
                    text: "ReyOS Reader"
                    level: 2
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }

        property var navItems: [
            { text: "Library", icon: "view-list-icons", section: "library" },
            { text: "Favorites", icon: "starred-symbolic", section: "favorites" },
            { text: "Recently Added", icon: "document-open-recent", section: "recent" }
        ]
        property string currentSection: "library"

        Controls.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                width: drawer.width
                spacing: 0
                Repeater {
                    model: drawer.navItems
                    delegate: NavItem {
                        text: modelData.text
                        icon.name: modelData.icon
                        navHighlighted: drawer.currentSection === modelData.section
                        onClicked: {
                            appWindow.openLibraryHome()
                            drawer.currentSection = modelData.section
                            libraryPage.section = modelData.section
                        }
                    }
                }
                Kirigami.Separator { Layout.fillWidth: true; Layout.margins: Kirigami.Units.smallSpacing }
                NavItem {
                    text: "Open File..."
                    icon.name: "document-open"
                    onClicked: backend.openFileDialog()
                }
                NavItem {
                    text: "Add Folder..."
                    icon.name: "folder-new"
                    onClicked: backend.addFolder()
                }
                NavItem {
                    text: "Refresh Library"
                    icon.name: "view-refresh"
                    onClicked: backend.refreshLibrary()
                }
                Kirigami.Separator { Layout.fillWidth: true; Layout.margins: Kirigami.Units.smallSpacing }
                NavItem {
                    text: "PDF Tools"
                    icon.name: "document-multiple"
                    onClicked: {
                        appWindow.openLibraryHome()
                        pageStack.push(Qt.resolvedUrl("PdfToolsPage.qml"))
                    }
                }
            }
        }
    }

    // StackView.initialItem is a construction-time hook -- assigning it as
    // a dotted property from this outer document runs too late to take
    // effect (confirmed live: pageStack.depth stayed 0). Push explicitly.
    Component.onCompleted: pageStack.push(Qt.resolvedUrl("LibraryPage.qml"))

    // `pageStack.depth` is read here purely so this binding re-evaluates
    // once the Component.onCompleted push above actually happens --
    // pageStack.get(0) alone is a plain method call QML won't re-run when
    // the stack changes, so this stayed permanently null without it.
    property Item libraryPage: pageStack.depth > 0 ? pageStack.get(0) : null

    function openLibraryHome() {
        while (pageStack.depth > 1) {
            pageStack.pop()
        }
    }

    Connections {
        target: backend
        function onEpubReady(itemId, metaJson) {
            appWindow.openLibraryHome()
            pageStack.push(Qt.resolvedUrl("BookReaderPage.qml"), { meta: JSON.parse(metaJson) })
        }
        function onPdfReady(itemId, metaJson) {
            appWindow.openLibraryHome()
            pageStack.push(Qt.resolvedUrl("PdfReaderPage.qml"), { meta: JSON.parse(metaJson) })
        }
        function onPdfPreviewReady(metaJson) {
            // No openLibraryHome() here, deliberately -- this is reached
            // from PDF Tools' Split card "Preview" button, and popping back
            // to Library first would discard whatever files/range the user
            // already picked there. Pushing on top keeps PDF Tools
            // underneath so Back returns to it with that state intact.
            pageStack.push(Qt.resolvedUrl("PdfReaderPage.qml"), { meta: JSON.parse(metaJson) })
        }
        function onComicReady(itemId, metaJson) {
            appWindow.openLibraryHome()
            pageStack.push(Qt.resolvedUrl("ComicReaderPage.qml"), { meta: JSON.parse(metaJson) })
        }
        function onOpenFailed(message, technical) {
            errorDialog.message = message
            errorDialog.technical = technical
            errorDialog.open()
        }
    }

    Controls.Dialog {
        id: errorDialog
        property string message: ""
        property string technical: ""
        title: "Could not open file"
        modal: true
        standardButtons: Controls.Dialog.Ok
        x: (appWindow.width - width) / 2
        y: (appWindow.height - height) / 2
        width: Math.min(appWindow.width * 0.7, 480)

        ColumnLayout {
            width: parent.width
            spacing: Kirigami.Units.smallSpacing
            Controls.Label {
                text: errorDialog.message
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Kirigami.LinkButton {
                text: detailsRevealer.visible ? "Hide technical details" : "Technical details"
                visible: errorDialog.technical.length > 0
                onClicked: detailsRevealer.visible = !detailsRevealer.visible
            }
            Controls.ScrollView {
                id: detailsRevealer
                visible: false
                Layout.fillWidth: true
                Layout.preferredHeight: 120
                Controls.TextArea {
                    readOnly: true
                    text: errorDialog.technical
                    font.family: "monospace"
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    wrapMode: Text.Wrap
                }
            }
        }
    }

    Shortcut { sequence: "Ctrl+O"; onActivated: backend.openFileDialog() }
    Shortcut { sequence: "Ctrl+L"; onActivated: appWindow.openLibraryHome() }
    Shortcut {
        sequence: "F11"
        onActivated: {
            appWindow.distractionFree = !appWindow.distractionFree
            appWindow.visibility = appWindow.distractionFree ? Window.FullScreen : Window.Windowed
        }
    }
}
