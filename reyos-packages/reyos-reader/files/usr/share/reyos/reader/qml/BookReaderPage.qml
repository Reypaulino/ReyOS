import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtWebEngine
import "kirishim" as Kirigami
import "." as Reader
import "components" as Components

Kirigami.Page {
    id: page
    title: meta.title
    padding: 0

    property var meta
    property int currentChapter: meta.startChapter
    property real fontScale: 1.0
    property real lineSpacing: 1.5
    property real letterSpacing: 0.01
    property real marginPct: 8
    property string textAlign: "left"
    property string readTheme: "dark"   // dark | light | sepia
    property bool findBarVisible: false
    property var bookmarks: []
    property var highlights: []
    property var allHighlights: []
    property bool chromeVisible: true

    function reloadHighlights() {
        page.highlights = JSON.parse(backend.listHighlightsForChapter(meta.id, page.currentChapter))
    }

    function applyHighlightsToPage() {
        webView.runJavaScript(backend.highlighterScriptSource)
        webView.runJavaScript("window.__reyosApplyHighlights(" + JSON.stringify(JSON.stringify(page.highlights)) + ");")
    }

    function showChrome() {
        page.chromeVisible = true
        autoHideTimer.restart()
    }

    Timer {
        id: autoHideTimer
        interval: 3000
        onTriggered: if (!page.findBarVisible) page.chromeVisible = false
    }

    function reloadBookmarks() {
        page.bookmarks = JSON.parse(backend.listBookmarks(meta.id))
    }

    function currentBookmarkId() {
        for (var i = 0; i < page.bookmarks.length; i++) {
            if (page.bookmarks[i].location.chapter === page.currentChapter) return page.bookmarks[i].id
        }
        return -1
    }

    function toggleBookmark() {
        var existing = page.currentBookmarkId()
        if (existing !== -1) {
            backend.removeBookmark(existing)
        } else {
            backend.addBookmark(meta.id, JSON.stringify({ chapter: page.currentChapter }), "Chapter " + (page.currentChapter + 1))
        }
        page.reloadBookmarks()
    }

    function themeColors() {
        if (page.readTheme === "sepia") return { bg: Reader.ReyOSStyle.sepiaBg, fg: Reader.ReyOSStyle.sepiaText }
        if (page.readTheme === "light") return { bg: Reader.ReyOSStyle.lightReadBg, fg: Reader.ReyOSStyle.lightReadText }
        return { bg: Reader.ReyOSStyle.darkReadBg, fg: Reader.ReyOSStyle.darkReadText }
    }

    function applyAppearance() {
        var c = themeColors()
        var css = "body { background: " + c.bg + " !important; color: " + c.fg + " !important;" +
                  " font-family: Georgia, 'Liberation Serif', 'DejaVu Serif', serif !important;" +
                  " font-size: " + Math.round(fontScale * 100) + "% !important;" +
                  " line-height: " + lineSpacing + " !important;" +
                  " letter-spacing: " + letterSpacing + "em !important;" +
                  " word-spacing: " + (letterSpacing * 2.5) + "em !important;" +
                  " text-align: " + textAlign + " !important;" +
                  " padding-left: " + marginPct + "% !important; padding-right: " + marginPct + "% !important;" +
                  " max-width: none !important; }" +
                  " body * { color: inherit !important; background: transparent !important;" +
                  " line-height: inherit !important; letter-spacing: inherit !important; }" +
                  // Cover art and other embedded images often carry their own
                  // width/height attributes sized for a full e-reader page --
                  // with no cap here they render at that native pixel size
                  // inside our narrower reading column, forcing scrollbars
                  // just to see one image (confirmed live on a real cover).
                  " img, svg, image { max-width: 100% !important; max-height: 90vh !important;" +
                  " width: auto !important; height: auto !important; }"
        var js = "(function(){ var s = document.getElementById('reyos-reader-style');" +
                 "if(!s){ s = document.createElement('style'); s.id='reyos-reader-style'; document.head.appendChild(s); }" +
                 "s.textContent = " + JSON.stringify(css) + "; })();"
        webView.runJavaScript(js)
    }

    function restoreScroll(frac) {
        webView.runJavaScript(
            "window.scrollTo(0, document.documentElement.scrollHeight * " + frac + ");"
        )
    }

    function saveProgress() {
        webView.runJavaScript(
            "(document.documentElement.scrollTop || document.body.scrollTop) / " +
            "Math.max(1, (document.documentElement.scrollHeight - window.innerHeight))",
            function(frac) {
                var f = (typeof frac === "number" && isFinite(frac)) ? Math.max(0, Math.min(1, frac)) : 0
                var percent = ((page.currentChapter + f) / Math.max(1, meta.chapterCount)) * 100
                backend.saveProgress(meta.id, JSON.stringify({ chapter: page.currentChapter, scroll_frac: f }), percent)
            }
        )
    }

    function goToChapter(index, frac) {
        if (index < 0 || index >= meta.chapterCount) return
        page.currentChapter = index
        webView.url = meta.chapterUrls[index]
        pendingRestoreFrac = frac !== undefined ? frac : 0
    }

    property real pendingRestoreFrac: meta.startScrollFrac || 0

    Component.onCompleted: {
        webView.url = meta.chapterUrls[currentChapter]
        page.reloadBookmarks()
    }

    Component.onDestruction: {
        saveProgress()
        backend.closeEpub()
    }

    Timer {
        interval: 8000
        running: true
        repeat: true
        onTriggered: page.saveProgress()
    }

    header: Item {
        width: page.width
        height: page.chromeVisible ? headerColumn.implicitHeight : 0
        clip: true
        Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.InOutQuad } }
        HoverHandler { onHoveredChanged: if (hovered) page.showChrome() }

        ColumnLayout {
        id: headerColumn
        width: page.width
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            Controls.ToolButton {
                icon.name: "view-table-of-contents"
                text: "Contents"
                display: Controls.ToolButton.IconOnly
                onClicked: tocSheet.open()
            }
            Controls.ToolButton {
                icon.name: "go-previous"
                enabled: page.currentChapter > 0
                onClicked: page.goToChapter(page.currentChapter - 1)
            }
            Controls.Label { text: (page.currentChapter + 1) + " / " + meta.chapterCount }
            Controls.ToolButton {
                icon.name: "go-next"
                enabled: page.currentChapter < meta.chapterCount - 1
                onClicked: page.goToChapter(page.currentChapter + 1)
            }
            Item { Layout.fillWidth: true }
            Controls.ToolButton {
                icon.name: page.currentBookmarkId() !== -1 ? "bookmarks" : "bookmark-new"
                text: page.currentBookmarkId() !== -1 ? "Bookmarked" : "Bookmark"
                display: Controls.ToolButton.IconOnly
                onClicked: page.toggleBookmark()
            }
            Controls.ToolButton {
                icon.name: "view-list-text"
                text: "Bookmarks"
                display: Controls.ToolButton.IconOnly
                onClicked: { page.reloadBookmarks(); bookmarksSheet.open() }
            }
            Controls.ToolButton {
                icon.name: "draw-highlight"
                text: "Highlights"
                display: Controls.ToolButton.IconOnly
                onClicked: {
                    page.allHighlights = JSON.parse(backend.listHighlights(meta.id))
                    highlightsSheet.open()
                }
            }
            Controls.ToolButton {
                icon.name: "edit-find"
                display: Controls.ToolButton.IconOnly
                onClicked: page.findBarVisible = !page.findBarVisible
            }
            Controls.ToolButton {
                text: "Aa"
                onClicked: textSettingsPopup.open()
            }
            Controls.ToolButton {
                text: page.readTheme === "dark" ? "Dark" : (page.readTheme === "light" ? "Light" : "Sepia")
                onClicked: {
                    page.readTheme = page.readTheme === "dark" ? "light" : (page.readTheme === "light" ? "sepia" : "dark")
                    page.applyAppearance()
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            visible: page.findBarVisible
            Controls.TextField {
                id: findField
                Layout.fillWidth: true
                placeholderText: "Find in chapter..."
                onTextChanged: webView.findText(text)
                Keys.onReturnPressed: webView.findText(text)
            }
            Controls.ToolButton { icon.name: "go-up"; onClicked: webView.findText(findField.text, WebEngineView.FindBackward) }
            Controls.ToolButton { icon.name: "go-down"; onClicked: webView.findText(findField.text) }
            Controls.ToolButton { icon.name: "window-close"; onClicked: { page.findBarVisible = false; webView.findText("") } }
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
                text: "Chapter " + (page.currentChapter + 1) + " of " + meta.chapterCount
            }
            Item { Layout.fillWidth: true }
            Controls.Label {
                opacity: 0.7
                text: Math.round(((page.currentChapter + 1) / Math.max(1, meta.chapterCount)) * 100) + "%"
            }
        }
    }

    WebEngineView {
        id: webView
        anchors.fill: parent

        onLoadingChanged: function(loadRequest) {
            if (loadRequest.status === WebEngineView.LoadSucceededStatus) {
                page.applyAppearance()
                page.restoreScroll(page.pendingRestoreFrac)
                page.pendingRestoreFrac = 0
                page.reloadHighlights()
                page.applyHighlightsToPage()
            }
        }

        onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceID) {
            if (message.indexOf("REYOS_HIGHLIGHT_NEW:") === 0) {
                var payload = JSON.parse(message.substring("REYOS_HIGHLIGHT_NEW:".length))
                var rangeJson = JSON.stringify({ start: payload.start, end: payload.end })
                backend.addHighlight(meta.id, page.currentChapter, rangeJson, payload.color, payload.snippet, "")
                page.reloadHighlights()
                Qt.callLater(page.applyHighlightsToPage)
            } else if (message.indexOf("REYOS_HIGHLIGHT_CLICK:") === 0) {
                var hlId = parseInt(message.substring("REYOS_HIGHLIGHT_CLICK:".length), 10)
                backend.removeHighlight(hlId)
                page.reloadHighlights()
                Qt.callLater(page.applyHighlightsToPage)
            }
        }
    }

    // Click the page edges to turn chapters, Kindle-style, without needing
    // the toolbar's prev/next buttons. Narrow enough (7%) to mostly land in
    // the reading margin rather than over real text.
    MouseArea {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width * 0.07
        cursorShape: Qt.PointingHandCursor
        onClicked: page.goToChapter(page.currentChapter - 1)
    }
    MouseArea {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width * 0.07
        cursorShape: Qt.PointingHandCursor
        onClicked: page.goToChapter(page.currentChapter + 1)
    }

    // Always-present reveal handle while the toolbar/status bar are
    // auto-hidden -- hovering or clicking it brings the chrome back, same
    // idea as a fullscreen video player's "show controls" strip.
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

    // Kindle-style: tapping the top-right corner of the page toggles the
    // bookmark, whether or not one already exists yet. This needs its own
    // always-active hit target, separate from BookmarkRibbon's visual --
    // that ribbon is only *visible* once a bookmark exists, and an
    // invisible Item receives no input, so before the first tap this
    // corner silently fell through to the "next chapter" edge MouseArea
    // above instead of creating a bookmark (confirmed live: clicking the
    // corner did nothing but occasionally flip pages).
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

    Controls.Popup {
        id: textSettingsPopup
        x: page.width - width - Kirigami.Units.largeSpacing
        y: page.header.height
        width: 280
        modal: false
        focus: true
        closePolicy: Controls.Popup.CloseOnEscape | Controls.Popup.CloseOnPressOutsideParent

        ColumnLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.largeSpacing

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading { Layout.fillWidth: true; level: 4; text: "Text Settings" }
                Controls.ToolButton {
                    icon.name: "window-close"
                    onClicked: textSettingsPopup.close()
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                Controls.Label { text: "Font Size" }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.ToolButton { icon.name: "format-font-size-less"; onClicked: { page.fontScale = Math.max(0.6, page.fontScale - 0.1); page.applyAppearance() } }
                    Controls.Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: Math.round(page.fontScale * 100) + "%" }
                    Controls.ToolButton { icon.name: "format-font-size-more"; onClicked: { page.fontScale = Math.min(2.5, page.fontScale + 0.1); page.applyAppearance() } }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                Controls.Label { text: "Line Spacing" }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.ToolButton { icon.name: "list-remove"; onClicked: { page.lineSpacing = Math.max(1.0, page.lineSpacing - 0.1); page.applyAppearance() } }
                    Controls.Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: page.lineSpacing.toFixed(1) }
                    Controls.ToolButton { icon.name: "list-add"; onClicked: { page.lineSpacing = Math.min(2.5, page.lineSpacing + 0.1); page.applyAppearance() } }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                Controls.Label { text: "Letter Spacing" }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.ToolButton { icon.name: "list-remove"; onClicked: { page.letterSpacing = Math.max(0.0, page.letterSpacing - 0.01); page.applyAppearance() } }
                    Controls.Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: page.letterSpacing.toFixed(2) + "em" }
                    Controls.ToolButton { icon.name: "list-add"; onClicked: { page.letterSpacing = Math.min(0.15, page.letterSpacing + 0.01); page.applyAppearance() } }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                Controls.Label { text: "Margins" }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.ToolButton { icon.name: "list-remove"; onClicked: { page.marginPct = Math.max(0, page.marginPct - 2); page.applyAppearance() } }
                    Controls.Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: page.marginPct + "%" }
                    Controls.ToolButton { icon.name: "list-add"; onClicked: { page.marginPct = Math.min(20, page.marginPct + 2); page.applyAppearance() } }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Controls.Button {
                    Layout.fillWidth: true
                    text: "Left"
                    checkable: true
                    checked: page.textAlign === "left"
                    onClicked: { page.textAlign = "left"; page.applyAppearance() }
                }
                Controls.Button {
                    Layout.fillWidth: true
                    text: "Justify"
                    checkable: true
                    checked: page.textAlign === "justify"
                    onClicked: { page.textAlign = "justify"; page.applyAppearance() }
                }
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
                            text: modelData.label || ("Chapter " + (modelData.location.chapter + 1))
                            elide: Text.ElideRight
                        }
                        Controls.ToolButton {
                            icon.name: "edit-delete"
                            onClicked: { backend.removeBookmark(modelData.id); page.reloadBookmarks() }
                        }
                    }
                    onClicked: {
                        page.goToChapter(modelData.location.chapter)
                        bookmarksSheet.close()
                    }
                }
            }
        }
    }

    Kirigami.OverlaySheet {
        id: highlightsSheet
        title: "Highlights"
        ColumnLayout {
            implicitWidth: 380
            spacing: Kirigami.Units.smallSpacing

            Kirigami.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.largeSpacing
                visible: page.allHighlights.length === 0
                icon.name: "draw-highlight"
                text: "No highlights yet"
                explanation: "Select some text while reading to highlight it."
            }
            Repeater {
                model: page.allHighlights
                delegate: Controls.ItemDelegate {
                    required property var modelData
                    Layout.fillWidth: true
                    padding: Kirigami.Units.smallSpacing
                    hoverEnabled: false
                    down: false
                    contentItem: ColumnLayout {
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Rectangle {
                                width: 14; height: 14; radius: 3
                                color: modelData.color
                                border.color: Qt.rgba(0, 0, 0, 0.3)
                            }
                            Controls.Label {
                                Layout.fillWidth: true
                                text: "Chapter " + (modelData.chapter + 1)
                                opacity: 0.7
                                font.pixelSize: 12
                            }
                            Controls.ToolButton {
                                icon.name: "go-jump"
                                Controls.ToolTip.visible: hovered
                                Controls.ToolTip.text: "Go to this highlight"
                                onClicked: {
                                    page.goToChapter(modelData.chapter)
                                    highlightsSheet.close()
                                }
                            }
                            Controls.ToolButton {
                                icon.name: "edit-delete"
                                onClicked: {
                                    backend.removeHighlight(modelData.id)
                                    page.allHighlights = JSON.parse(backend.listHighlights(meta.id))
                                    if (modelData.chapter === page.currentChapter) {
                                        page.reloadHighlights()
                                        Qt.callLater(page.applyHighlightsToPage)
                                    }
                                }
                            }
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: "“" + modelData.snippet + "”"
                            wrapMode: Text.Wrap
                            font.italic: true
                        }
                        Controls.TextField {
                            Layout.fillWidth: true
                            placeholderText: "Add a note…"
                            text: modelData.note || ""
                            onEditingFinished: backend.updateHighlightNote(modelData.id, text)
                        }
                    }
                }
            }
            Controls.Button {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                visible: page.allHighlights.length > 0
                text: "Export Highlights…"
                icon.name: "document-save"
                onClicked: backend.exportHighlights(meta.id)
            }
        }
    }

    Kirigami.OverlaySheet {
        id: tocSheet
        title: "Contents"
        ListView {
            implicitWidth: 320
            implicitHeight: Math.min(400, meta.toc.length * 40)
            model: meta.toc
            delegate: Controls.ItemDelegate {
                width: ListView.view.width
                text: modelData.title
                onClicked: {
                    var idx = meta.chapterUrls.findIndex(function(u) { return u.indexOf(modelData.href) !== -1 })
                    if (idx === -1) idx = page.currentChapter
                    page.goToChapter(idx)
                    tocSheet.close()
                }
            }
        }
    }

    Shortcut { sequence: "Ctrl+F"; onActivated: page.findBarVisible = true }
    Shortcut { sequence: "Ctrl++"; onActivated: { page.fontScale = Math.min(2.5, page.fontScale + 0.1); page.applyAppearance() } }
    Shortcut { sequence: "Ctrl+-"; onActivated: { page.fontScale = Math.max(0.6, page.fontScale - 0.1); page.applyAppearance() } }
    Shortcut { sequence: "Ctrl+0"; onActivated: { page.fontScale = 1.0; page.applyAppearance() } }
    Shortcut { sequence: "B"; enabled: !findField.activeFocus; onActivated: page.toggleBookmark() }
    Shortcut { sequence: "PgDown"; onActivated: page.goToChapter(page.currentChapter + 1) }
    Shortcut { sequence: "PgUp"; onActivated: page.goToChapter(page.currentChapter - 1) }
}
