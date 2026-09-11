import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "kirishim" as Kirigami
import "components" as Components

Kirigami.Page {
    id: page
    title: meta.title
    padding: 0

    property var meta
    property string direction: meta.direction || "ltr"     // ltr | rtl
    property string viewMode: meta.viewMode || "single"     // single | double | continuous | webtoon
    property real zoomFactor: meta.zoom > 0 ? meta.zoom : 1.0
    property int currentIndex: meta.startPage || 0
    property bool horizontal: page.viewMode === "single" || page.viewMode === "double"
    property var pageUnits: []
    property var bookmarks: []
    property bool chromeVisible: true

    function showChrome() {
        page.chromeVisible = true
        autoHideTimer.restart()
    }

    Timer {
        id: autoHideTimer
        interval: 3000
        onTriggered: page.chromeVisible = false
    }

    function currentPageNumber() {
        return page.horizontal
            ? page.pageUnits[Math.max(0, Math.min(flick.currentIndex, page.pageUnits.length - 1))].a
            : page.currentIndex
    }

    function reloadBookmarks() {
        page.bookmarks = JSON.parse(backend.listBookmarks(meta.id))
    }

    function currentBookmarkId() {
        var p = page.currentPageNumber()
        for (var i = 0; i < page.bookmarks.length; i++) {
            if (page.bookmarks[i].location.page === p) return page.bookmarks[i].id
        }
        return -1
    }

    function toggleBookmark() {
        var existing = page.currentBookmarkId()
        if (existing !== -1) {
            backend.removeBookmark(existing)
        } else {
            var p = page.currentPageNumber()
            backend.addBookmark(meta.id, JSON.stringify({ page: p }), "Page " + (p + 1))
        }
        page.reloadBookmarks()
    }

    function rebuildUnits() {
        var units = []
        if (page.viewMode === "double") {
            for (var i = 0; i < meta.pageCount; i += 2) {
                units.push({ a: i, b: (i + 1 < meta.pageCount) ? i + 1 : -1 })
            }
        } else {
            for (var j = 0; j < meta.pageCount; j++) {
                units.push({ a: j, b: -1 })
            }
        }
        page.pageUnits = units
    }
    Component.onCompleted: { rebuildUnits(); page.reloadBookmarks() }
    onViewModeChanged: rebuildUnits()

    function unitIndexForPage(p) {
        for (var i = 0; i < page.pageUnits.length; i++) {
            if (page.pageUnits[i].a === p || page.pageUnits[i].b === p) return i
        }
        return 0
    }

    function next() {
        if (page.horizontal) flick.currentIndex = Math.min(flick.currentIndex + 1, page.pageUnits.length - 1)
        else flick.contentY += flick.height * 0.9
    }
    function prev() {
        if (page.horizontal) flick.currentIndex = Math.max(flick.currentIndex - 1, 0)
        else flick.contentY -= flick.height * 0.9
    }

    function saveProgress() {
        var p = page.horizontal
            ? page.pageUnits[Math.max(0, Math.min(flick.currentIndex, page.pageUnits.length - 1))].a
            : page.currentIndex
        var percent = ((p + 1) / Math.max(1, meta.pageCount)) * 100
        backend.saveProgress(meta.id, JSON.stringify({ page: p }), percent)
        backend.setZoom(meta.id, page.zoomFactor)
    }

    Component.onDestruction: {
        page.saveProgress()
        backend.closeComic(meta.id)
    }

    Timer { interval: 8000; running: true; repeat: true; onTriggered: page.saveProgress() }

    header: Item {
        width: page.width
        height: page.chromeVisible ? headerRow.implicitHeight : 0
        clip: true
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.InOutQuad } }
        HoverHandler { onHoveredChanged: if (hovered) page.showChrome() }

        RowLayout {
        id: headerRow
        width: page.width
        Layout.margins: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Controls.ToolButton { icon.name: "go-previous"; onClicked: page.prev() }
        Controls.Label {
            text: page.horizontal
                ? ((flick.currentIndex + 1) + " / " + page.pageUnits.length)
                : ((page.currentIndex + 1) + " / " + meta.pageCount)
        }
        Controls.ToolButton { icon.name: "go-next"; onClicked: page.next() }

        Controls.ComboBox {
            model: ["Single Page", "Double Page", "Continuous", "Webtoon"]
            currentIndex: ["single", "double", "continuous", "webtoon"].indexOf(page.viewMode)
            onActivated: {
                var modes = ["single", "double", "continuous", "webtoon"]
                page.viewMode = modes[currentIndex]
                backend.setViewMode(meta.id, page.viewMode)
            }
        }
        Controls.ComboBox {
            model: ["Left to Right", "Right to Left (Manga)"]
            currentIndex: page.direction === "rtl" ? 1 : 0
            onActivated: {
                page.direction = currentIndex === 1 ? "rtl" : "ltr"
                backend.setReadingDirection(meta.id, page.direction)
            }
        }

        Item { Layout.fillWidth: true }
        Controls.ToolButton { icon.name: "zoom-out"; onClicked: page.zoomFactor = Math.max(0.3, page.zoomFactor - 0.1) }
        Controls.Label { text: Math.round(page.zoomFactor * 100) + "%" }
        Controls.ToolButton { icon.name: "zoom-in"; onClicked: page.zoomFactor = Math.min(4, page.zoomFactor + 0.1) }
        Controls.ToolButton { icon.name: "zoom-original"; onClicked: page.zoomFactor = 1.0 }
        Controls.ToolButton {
            icon.name: page.currentBookmarkId() !== -1 ? "bookmarks" : "bookmark-new"
            onClicked: page.toggleBookmark()
        }
        Controls.ToolButton {
            icon.name: "view-list-text"
            onClicked: { page.reloadBookmarks(); bookmarksSheet.open() }
        }
        }
    }

    footer: Item {
        width: page.width
        height: page.chromeVisible ? footerRow.implicitHeight : 0
        clip: true
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.InOutQuad } }
        HoverHandler { onHoveredChanged: if (hovered) page.showChrome() }

        RowLayout {
            id: footerRow
            anchors.margins: Kirigami.Units.smallSpacing
            anchors.left: parent.left
            anchors.right: parent.right

            Controls.Label {
                opacity: 0.7
                text: page.horizontal
                    ? ("Page " + (flick.currentIndex + 1) + " of " + page.pageUnits.length)
                    : ("Page " + (page.currentIndex + 1) + " of " + meta.pageCount)
            }
            Item { Layout.fillWidth: true }
            Controls.Label {
                opacity: 0.7
                text: Math.round(((page.currentPageNumber() + 1) / Math.max(1, meta.pageCount)) * 100) + "%"
            }
        }
    }

    Kirigami.OverlaySheet {
        id: bookmarksSheet
        title: "Bookmarks"
        ColumnLayout {
            implicitWidth: 340
            spacing: Kirigami.Units.smallSpacing

            Kirigami.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.largeSpacing
                visible: page.bookmarks.length === 0
                icon.name: "bookmark-new"
                text: "No bookmarks yet"
                explanation: "Use the bookmark button or press B to save your place."
            }
            Repeater {
                model: page.bookmarks
                delegate: Controls.ItemDelegate {
                    Layout.fillWidth: true
                    padding: Kirigami.Units.smallSpacing
                    contentItem: RowLayout {
                        spacing: Kirigami.Units.smallSpacing
                        Kirigami.Icon {
                            source: "bookmarks"
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Kirigami.Units.iconSizes.small
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: modelData.label || ("Page " + (modelData.location.page + 1))
                            elide: Text.ElideRight
                        }
                        Controls.ToolButton {
                            icon.name: "edit-delete"
                            onClicked: { backend.removeBookmark(modelData.id); page.reloadBookmarks() }
                        }
                    }
                    onClicked: {
                        if (page.horizontal) {
                            flick.currentIndex = page.unitIndexForPage(modelData.location.page)
                        } else {
                            continuousList.positionViewAtIndex(modelData.location.page, ListView.Beginning)
                        }
                        bookmarksSheet.close()
                    }
                }
            }
        }
    }

    // -- horizontal single/double-page mode ------------------------------
    ListView {
        id: flick
        anchors.fill: parent
        visible: page.horizontal
        orientation: ListView.Horizontal
        layoutDirection: page.direction === "rtl" ? Qt.RightToLeft : Qt.LeftToRight
        snapMode: ListView.SnapOneItem
        highlightMoveDuration: 120
        cacheBuffer: page.width * 3
        model: page.pageUnits
        currentIndex: page.unitIndexForPage(page.currentIndex)

        delegate: Item {
            width: flick.width
            height: flick.height
            RowLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                layoutDirection: page.direction === "rtl" ? Qt.RightToLeft : Qt.LeftToRight
                spacing: 2
                Image {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    source: "image://reyospage/" + meta.id + "/" + modelData.a
                    Controls.BusyIndicator { anchors.centerIn: parent; running: parent.status === Image.Loading; visible: running }
                }
                Image {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: modelData.b >= 0
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    source: modelData.b >= 0 ? ("image://reyospage/" + meta.id + "/" + modelData.b) : ""
                }
            }
        }

        MouseArea {
            anchors.left: parent.left
            width: parent.width * 0.25
            height: parent.height
            onClicked: page.direction === "rtl" ? page.next() : page.prev()
        }
        MouseArea {
            anchors.right: parent.right
            width: parent.width * 0.25
            height: parent.height
            onClicked: page.direction === "rtl" ? page.prev() : page.next()
        }

        focus: true
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Right) { page.direction === "rtl" ? page.prev() : page.next(); event.accepted = true }
            else if (event.key === Qt.Key_Left) { page.direction === "rtl" ? page.next() : page.prev(); event.accepted = true }
            else if (event.key === Qt.Key_Space || event.key === Qt.Key_PageDown) { page.next(); event.accepted = true }
            else if (event.key === Qt.Key_PageUp) { page.prev(); event.accepted = true }
        }
    }

    // -- continuous / webtoon mode -----------------------------------------
    ListView {
        id: continuousList
        anchors.fill: parent
        visible: !page.horizontal
        model: meta.pageCount
        spacing: page.viewMode === "webtoon" ? 0 : Kirigami.Units.smallSpacing
        cacheBuffer: height * 2
        Controls.ScrollBar.vertical: Controls.ScrollBar {}

        delegate: Item {
            width: continuousList.width
            height: pageImage.height
            Image {
                id: pageImage
                anchors.horizontalCenter: parent.horizontalCenter
                width: continuousList.width * page.zoomFactor
                height: 600
                fillMode: Image.PreserveAspectFit
                asynchronous: true
                source: "image://reyospage/" + meta.id + "/" + index
                onStatusChanged: {
                    if (status === Image.Ready && sourceSize.width > 0) {
                        height = width * (sourceSize.height / sourceSize.width)
                    }
                }
            }
        }

        onContentYChanged: {
            var idx = continuousList.indexAt(continuousList.width / 2, continuousList.contentY + 10)
            if (idx >= 0) page.currentIndex = idx
        }
    }

    Rectangle {
        id: revealHandle
        visible: !page.chromeVisible
        z: 20
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.topMargin: 4
        width: 64
        height: 6
        radius: 3
        color: Qt.rgba(1, 1, 1, 0.35)
        HoverHandler { onHoveredChanged: if (hovered) page.showChrome() }
        MouseArea { anchors.fill: parent; onClicked: page.showChrome() }
    }

    // Kindle-style: tapping the top-right corner toggles the bookmark
    // whether or not one exists yet -- see BookReaderPage.qml for why this
    // needs its own always-active hit target instead of relying on
    // BookmarkRibbon's own (visible-only) MouseArea.
    Item {
        z: 20
        anchors.top: parent.top
        anchors.right: parent.right
        width: 56
        height: 64

        Components.BookmarkRibbon {
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: -1
            anchors.rightMargin: 20
            visible: page.currentBookmarkId() !== -1
            onClicked: page.toggleBookmark()
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: page.toggleBookmark()
        }
    }

    Shortcut { sequence: "Ctrl++"; onActivated: page.zoomFactor = Math.min(4, page.zoomFactor + 0.1) }
    Shortcut { sequence: "Ctrl+-"; onActivated: page.zoomFactor = Math.max(0.3, page.zoomFactor - 0.1) }
    Shortcut { sequence: "Ctrl+0"; onActivated: page.zoomFactor = 1.0 }
    Shortcut { sequence: "B"; onActivated: page.toggleBookmark() }
}
