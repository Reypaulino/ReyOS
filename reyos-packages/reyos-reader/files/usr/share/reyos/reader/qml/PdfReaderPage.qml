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

    PdfDocument {
        id: doc
        source: meta.path
        onStatusChanged: {
            if (status === PdfDocument.Ready && !page.restored) {
                page.restored = true
                view.goToPage(meta.startPage)
                if (meta.zoom > 0) view.renderScale = meta.zoom
            }
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

    header: RowLayout {
        width: page.width
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
        Controls.ToolButton { icon.name: "zoom-out"; onClicked: view.renderScale = Math.max(0.2, view.renderScale - 0.1) }
        Controls.Label { text: Math.round(view.renderScale * 100) + "%" }
        Controls.ToolButton { icon.name: "zoom-in"; onClicked: view.renderScale = Math.min(6, view.renderScale + 0.1) }
        Controls.ToolButton { icon.name: "zoom-original"; onClicked: view.resetScale() }
        Controls.ToolButton { icon.name: "zoom-fit-width"; onClicked: view.scaleToWidth(page.width - 40, page.height) }
    }

    PdfMultiPageView {
        id: view
        anchors.fill: parent
        document: doc

        Keys.onPressed: function(event) {
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

    Shortcut { sequence: "Ctrl++"; onActivated: view.renderScale = Math.min(6, view.renderScale + 0.1) }
    Shortcut { sequence: "Ctrl+-"; onActivated: view.renderScale = Math.max(0.2, view.renderScale - 0.1) }
    Shortcut { sequence: "Ctrl+0"; onActivated: view.resetScale() }
}
