import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "kirishim" as Kirigami
import "components" as Components

Kirigami.ScrollablePage {
    id: page
    title: "ReyOS Reader"

    property string section: "library"   // library | favorites | recent
    property string filter: "all"        // all | books | manga | comics | pdfs
    property string searchText: ""

    property var libraryItems: []
    property var continueItems: []

    function reload() {
        var json
        if (page.section === "favorites") {
            json = backend.getFavorites()
        } else if (page.section === "recent") {
            json = backend.getRecentlyAdded()
        } else if (page.searchText.length > 0) {
            json = backend.search(page.searchText)
        } else {
            json = backend.getLibrary(page.filter)
        }
        page.libraryItems = JSON.parse(json)
        page.continueItems = JSON.parse(backend.getContinueReading())
    }

    Component.onCompleted: reload()

    Connections {
        target: backend
        function onLibraryChanged() { page.reload() }
    }

    onSectionChanged: reload()
    onFilterChanged: reload()

    actions: [
        Kirigami.Action {
            icon.name: "document-open"
            text: "Open File"
            onTriggered: backend.openFileDialog()
        },
        Kirigami.Action {
            icon.name: "folder-new"
            text: "Add Folder"
            onTriggered: backend.addFolder()
        },
        Kirigami.Action {
            icon.name: "view-refresh"
            text: "Refresh"
            onTriggered: backend.refreshLibrary()
        }
    ]

    header: ColumnLayout {
        width: page.width
        spacing: Kirigami.Units.smallSpacing
        visible: page.section === "library"

        Kirigami.SearchField {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            placeholderText: "Search title or author..."
            onTextChanged: { page.searchText = text; page.reload() }
        }

        RowLayout {
            Layout.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing
            Repeater {
                model: [
                    { label: "All", value: "all" },
                    { label: "Books", value: "books" },
                    { label: "Manga", value: "manga" },
                    { label: "Comics", value: "comics" },
                    { label: "PDFs", value: "pdfs" }
                ]
                delegate: Controls.Button {
                    text: modelData.label
                    checkable: true
                    checked: page.filter === modelData.value
                    onClicked: page.filter = modelData.value
                }
            }
        }
    }

    ColumnLayout {
        width: page.width
        spacing: Kirigami.Units.largeSpacing

        ColumnLayout {
            Layout.fillWidth: true
            visible: page.section === "library" && page.continueItems.length > 0 && page.searchText.length === 0
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Heading {
                text: "Continue Reading"
                level: 3
            }
            Flickable {
                Layout.fillWidth: true
                Layout.preferredHeight: 190
                contentWidth: continueRow.implicitWidth
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                RowLayout {
                    id: continueRow
                    spacing: Kirigami.Units.largeSpacing
                    Repeater {
                        model: page.continueItems
                        delegate: Components.ContinueReadingCard {
                            item: modelData
                            onResume: backend.openItem(modelData.id)
                        }
                    }
                }
            }
        }

        Kirigami.Heading {
            level: 3
            text: page.section === "favorites" ? "Favorites" : (page.section === "recent" ? "Recently Added" : "Library")
        }

        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            visible: page.libraryItems.length === 0
            icon.name: "folder-open"
            text: "No items here yet"
            explanation: "Use “Add Folder” or “Open File” to bring books, manga, and comics into ReyOS Reader."
        }

        GridLayout {
            Layout.fillWidth: true
            visible: page.libraryItems.length > 0
            columns: Math.max(2, Math.floor(page.width / 190))
            columnSpacing: Kirigami.Units.largeSpacing
            rowSpacing: Kirigami.Units.largeSpacing

            Repeater {
                model: page.libraryItems
                delegate: Components.LibraryCard {
                    item: modelData
                    onOpen: backend.openItem(modelData.id)
                    onToggleFavorite: backend.setFavorite(modelData.id, !modelData.favorite)
                    onRemove: backend.removeFromLibrary(modelData.id)
                }
            }
        }
    }
}
