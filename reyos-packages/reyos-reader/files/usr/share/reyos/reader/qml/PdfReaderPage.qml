import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import QtQuick.Pdf
import "kirishim" as Kirigami

Kirigami.Page {
    id: page
    title: meta.title
    padding: 0

    property var meta
    property bool restored: false

    // Set right before breaking doc.source's binding to reload the file
    // after an annotation write -- QPdfDocument has no live-reload/refresh
    // API, so the only way to see a freshly-saved annotation is to clear
    // and re-set source, which drops page/zoom state unless we restore it
    // ourselves once the reload's own Ready status fires.
    property bool awaitingReload: false
    property int pendingReloadPage: 0
    property real pendingReloadScale: 1

    property bool findBarVisible: false

    function reloadAnnotations() {
        var json = backend.getPdfAnnotations(meta.path)
        try {
            view.annotations = JSON.parse(json)
        } catch (e) {
            view.annotations = []
        }
    }

    PdfDocument {
        id: doc
        source: meta.path
        onStatusChanged: function() {
            if (doc.status === PdfDocument.Ready) {
                if (!page.restored) {
                    page.restored = true
                    view.goToPage(meta.startPage)
                    if (meta.zoom > 0) view.renderScale = meta.zoom
                    page.reloadAnnotations()
                } else if (page.awaitingReload) {
                    page.awaitingReload = false
                    // A same-tick goToPage() here (mirroring the first-load
                    // branch above) reliably lands on page 0 instead, and a
                    // single Qt.callLater() turn wasn't enough either -- the
                    // TableView's page-size/geometry cache from the *old*
                    // source apparently takes a moment longer than either to
                    // finish invalidating after this reload path specifically.
                    reloadRestoreTimer.start()
                }
            }
        }
    }

    Timer {
        id: reloadRestoreTimer
        interval: 200
        onTriggered: {
            view.goToPage(page.pendingReloadPage)
            view.renderScale = page.pendingReloadScale
            page.reloadAnnotations()
        }
    }

    function reloadAfterAnnotation() {
        page.pendingReloadPage = view.currentPage
        page.pendingReloadScale = view.renderScale
        page.awaitingReload = true
        doc.source = ""
        doc.source = meta.path
    }

    Connections {
        target: backend
        function onPdfAnnotationAdded() {
            resultBanner.visible = false
            page.reloadAfterAnnotation()
        }
        function onPdfAnnotationFailed(message) {
            resultBanner.resultOk = false
            resultBanner.text = message
            resultBanner.visible = true
        }
    }

    function saveProgress() {
        if (doc.pageCount <= 0) return
        var percent = ((view.currentPage + 1) / doc.pageCount) * 100
        backend.saveProgress(meta.id, JSON.stringify({ page: view.currentPage }), percent)
        backend.setZoom(meta.id, view.renderScale)
    }

    Component.onDestruction: page.saveProgress()

    Timer { interval: 8000; running: true; repeat: true; onTriggered: page.saveProgress() }

    header: ColumnLayout {
        width: page.width
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            Controls.ToolButton {
                icon.name: "go-previous"
                enabled: view.currentPage > 0
                onClicked: view.goToPage(view.currentPage - 1)
            }
            Controls.Label { text: (view.currentPage + 1) + " / " + doc.pageCount }
            Controls.ToolButton {
                icon.name: "go-next"
                enabled: view.currentPage < doc.pageCount - 1
                onClicked: view.goToPage(view.currentPage + 1)
            }
            Item { Layout.fillWidth: true }
            Controls.ToolButton {
                icon.name: "edit-find"
                checkable: true
                checked: page.findBarVisible
                onClicked: page.findBarVisible = !page.findBarVisible
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Find in document"
            }
            Controls.ToolButton {
                icon.name: "draw-highlight"
                enabled: view.selectedText.length > 0
                onClicked: backend.addPdfHighlight(meta.path, view.currentPage, view.selectedText)
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Highlight selected text"
            }
            Controls.ToolButton {
                icon.name: "insert-text"
                onClicked: placeDialog.openFor("text")
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Add text"
            }
            Controls.ToolButton {
                icon.name: "view-pim-notes"
                onClicked: placeDialog.openFor("comment")
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Add comment"
            }
            Controls.ToolButton { icon.name: "zoom-out"; onClicked: view.renderScale = Math.max(0.2, view.renderScale - 0.1) }
            Controls.Label { text: Math.round(view.renderScale * 100) + "%" }
            Controls.ToolButton { icon.name: "zoom-in"; onClicked: view.renderScale = Math.min(6, view.renderScale + 0.1) }
            Controls.ToolButton { icon.name: "zoom-original"; onClicked: view.resetScale() }
            Controls.ToolButton { icon.name: "zoom-fit-width"; onClicked: view.scaleToWidth(page.width - 40, page.height) }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing
            visible: page.findBarVisible

            Controls.TextField {
                id: findField
                Layout.fillWidth: true
                placeholderText: "Find in document..."
                onTextChanged: view.searchString = text
                Keys.onReturnPressed: view.searchForward()
            }
            Controls.Label {
                text: view.searchModel.count > 0
                    ? (view.searchModel.currentResult + 1) + " / " + view.searchModel.count
                    : (findField.text.length > 0 ? "No results" : "")
            }
            Controls.ToolButton { icon.name: "go-up"; enabled: view.searchModel.count > 0; onClicked: view.searchBack() }
            Controls.ToolButton { icon.name: "go-down"; enabled: view.searchModel.count > 0; onClicked: view.searchForward() }
            Controls.ToolButton {
                icon.name: "window-close"
                onClicked: { page.findBarVisible = false; findField.text = ""; view.searchString = "" }
            }
        }

        Kirigami.InlineMessage {
            id: resultBanner
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.smallSpacing
            visible: false
            property bool resultOk: true
            type: resultOk ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            showCloseButton: true
        }
    }

    PdfAnnotatedMultiPageView {
        id: view
        anchors.fill: parent
        document: doc

        onAnnotationTapped: function(annotation) {
            annotationInfoPopup.text = annotation.text
            annotationInfoPopup.open()
        }

        Keys.onPressed: function(event) {
            if (findField.activeFocus) return
            if (event.key === Qt.Key_PageDown || event.key === Qt.Key_Space || event.key === Qt.Key_Right || event.key === Qt.Key_Down) {
                view.goToPage(view.currentPage + 1)
                event.accepted = true
            } else if (event.key === Qt.Key_PageUp || event.key === Qt.Key_Left || event.key === Qt.Key_Up) {
                view.goToPage(view.currentPage - 1)
                event.accepted = true
            }
        }
        Component.onCompleted: forceActiveFocus()
    }

    Controls.Popup {
        id: annotationInfoPopup
        anchors.centerIn: parent
        modal: true
        width: Math.min(page.width - 80, 420)
        property alias text: infoLabel.text

        ColumnLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing
            Controls.Label {
                id: infoLabel
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Controls.Button {
                Layout.alignment: Qt.AlignRight
                text: "Close"
                onClicked: annotationInfoPopup.close()
            }
        }
    }

    // Placing a free-text note or a comment needs a page-point position.
    // PdfAnnotatedMultiPageView (the fork above) could expose that too, but
    // this dialog predates the fork and works fine as is: it renders the
    // current page on its own via PdfPageImage (a plain Image subclass) at
    // a size this dialog controls, so the click-to-page-point scale factor
    // is simple, known math instead of read off the live scrolling/zooming
    // view.
    Controls.Popup {
        id: placeDialog
        anchors.centerIn: parent
        modal: true
        focus: true
        width: Math.min(page.width - 60, 640)
        height: Math.min(page.height - 60, 760)

        property string mode: "text"
        property size pagePointSize: doc.status === PdfDocument.Ready ? doc.pagePointSize(view.currentPage) : Qt.size(1, 1)
        property real pointX: -1
        property real pointY: -1

        function openFor(mode) {
            placeDialog.mode = mode
            placeDialog.pointX = -1
            placeDialog.pointY = -1
            noteField.text = ""
            placeDialog.open()
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: placeDialog.mode === "comment"
                    ? "Tap where the comment should go, then type it below."
                    : "Tap where the text should go, then type it below."
            }

            Item {
                id: previewArea
                Layout.fillWidth: true
                Layout.fillHeight: true

                PdfPageImage {
                    id: previewImage
                    document: doc
                    currentFrame: view.currentPage
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectFit
                }

                property real scale: previewImage.paintedWidth / placeDialog.pagePointSize.width
                property real offsetX: (previewArea.width - previewImage.paintedWidth) / 2
                property real offsetY: (previewArea.height - previewImage.paintedHeight) / 2

                Rectangle {
                    visible: placeDialog.pointX >= 0
                    x: previewArea.offsetX + placeDialog.pointX * previewArea.scale - width / 2
                    y: previewArea.offsetY + placeDialog.pointY * previewArea.scale - height / 2
                    width: 14; height: 14; radius: 7
                    color: "transparent"
                    border.color: "red"
                    border.width: 2
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: function(mouse) {
                        var localX = mouse.x - previewArea.offsetX
                        var localY = mouse.y - previewArea.offsetY
                        if (localX < 0 || localY < 0 || localX > previewImage.paintedWidth || localY > previewImage.paintedHeight)
                            return
                        placeDialog.pointX = localX / previewArea.scale
                        placeDialog.pointY = localY / previewArea.scale
                    }
                }
            }

            Controls.TextArea {
                id: noteField
                Layout.fillWidth: true
                placeholderText: placeDialog.mode === "comment" ? "Comment text..." : "Text to add..."
                wrapMode: Controls.TextArea.Wrap
                Layout.preferredHeight: 80
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Controls.Button { text: "Cancel"; onClicked: placeDialog.close() }
                Controls.Button {
                    text: placeDialog.mode === "comment" ? "Add Comment" : "Add Text"
                    enabled: placeDialog.pointX >= 0 && noteField.text.trim().length > 0
                    onClicked: {
                        if (placeDialog.mode === "comment") {
                            backend.addPdfComment(meta.path, view.currentPage, placeDialog.pointX, placeDialog.pointY, noteField.text)
                        } else {
                            backend.addPdfFreeText(meta.path, view.currentPage, placeDialog.pointX, placeDialog.pointY, noteField.text)
                        }
                        placeDialog.close()
                    }
                }
            }
        }
    }

    Shortcut { sequence: "Ctrl++"; onActivated: view.renderScale = Math.min(6, view.renderScale + 0.1) }
    Shortcut { sequence: "Ctrl+-"; onActivated: view.renderScale = Math.max(0.2, view.renderScale - 0.1) }
    Shortcut { sequence: "Ctrl+0"; onActivated: view.resetScale() }
    Shortcut { sequence: "Ctrl+F"; onActivated: { page.findBarVisible = true; findField.forceActiveFocus() } }
}
