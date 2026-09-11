import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import "kirishim" as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "PDF Tools"

    property var mergeFiles: []
    property string splitFile: ""
    property int splitPageCount: 0

    property bool busy: false
    property string resultMessage: ""
    property bool resultOk: true

    Connections {
        target: backend
        function onPdfToolFinished(ok, message) {
            page.busy = false
            page.resultOk = ok
            page.resultMessage = ok ? ("Saved to " + message) : message
            resultBanner.visible = true
            if (ok) {
                page.mergeFiles = []
                page.splitFile = ""
                page.splitPageCount = 0
            }
        }
    }

    ColumnLayout {
        width: page.width
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            id: resultBanner
            Layout.fillWidth: true
            visible: false
            type: page.resultOk ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            text: page.resultMessage
            showCloseButton: true
        }

        // -- Merge -------------------------------------------------------
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Heading {
                    level: 3
                    text: "Merge PDFs"
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Combine multiple PDFs into one, in the order listed below. Originals are never modified."
                    opacity: 0.7
                }

                Repeater {
                    model: page.mergeFiles
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideMiddle
                            text: (index + 1) + ". " + modelData.split("/").pop()
                        }
                        Controls.ToolButton {
                            icon.name: "go-up"
                            enabled: index > 0
                            onClicked: {
                                var files = page.mergeFiles.slice()
                                var tmp = files[index - 1]
                                files[index - 1] = files[index]
                                files[index] = tmp
                                page.mergeFiles = files
                            }
                        }
                        Controls.ToolButton {
                            icon.name: "go-down"
                            enabled: index < page.mergeFiles.length - 1
                            onClicked: {
                                var files = page.mergeFiles.slice()
                                var tmp = files[index + 1]
                                files[index + 1] = files[index]
                                files[index] = tmp
                                page.mergeFiles = files
                            }
                        }
                        Controls.ToolButton {
                            icon.name: "edit-delete"
                            onClicked: {
                                var files = page.mergeFiles.slice()
                                files.splice(index, 1)
                                page.mergeFiles = files
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    Controls.Button {
                        text: "Add Files..."
                        icon.name: "list-add"
                        onClicked: {
                            var picked = backend.pickPdfsToMerge()
                            if (picked && picked.length > 0) {
                                page.mergeFiles = page.mergeFiles.concat(picked)
                            }
                        }
                    }
                    Item { Layout.fillWidth: true }
                    Controls.Button {
                        text: "Merge Into..."
                        icon.name: "document-save"
                        enabled: page.mergeFiles.length >= 2 && !page.busy
                        onClicked: {
                            var output = backend.pickPdfSaveAs("merged.pdf")
                            if (output) {
                                page.busy = true
                                backend.mergePdfs(page.mergeFiles, output)
                            }
                        }
                    }
                }
            }
        }

        // -- Split ---------------------------------------------------------
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Heading {
                    level: 3
                    text: "Split PDF"
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Extract specific pages from a PDF into a new file. The original is never modified."
                    opacity: 0.7
                }

                RowLayout {
                    Layout.fillWidth: true
                    Controls.Button {
                        text: "Choose PDF..."
                        icon.name: "document-open"
                        onClicked: {
                            var picked = backend.pickPdfToSplit()
                            if (picked) {
                                page.splitFile = picked
                                page.splitPageCount = backend.pdfPageCount(picked)
                            }
                        }
                    }
                    Controls.Button {
                        text: "Preview…"
                        icon.name: "document-preview"
                        enabled: page.splitFile.length > 0
                        onClicked: backend.previewPdf(page.splitFile)
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        text: page.splitFile.length > 0
                            ? (page.splitFile.split("/").pop() + " (" + page.splitPageCount + " pages)")
                            : "No file selected"
                        opacity: page.splitFile.length > 0 ? 1.0 : 0.6
                    }
                }

                Controls.TextField {
                    id: rangeField
                    Layout.fillWidth: true
                    enabled: page.splitFile.length > 0
                    placeholderText: "Pages to extract, e.g. 1-3,5,8-10"
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    Item { Layout.fillWidth: true }
                    Controls.Button {
                        text: "Split Into..."
                        icon.name: "document-save"
                        enabled: page.splitFile.length > 0 && rangeField.text.length > 0 && !page.busy
                        onClicked: {
                            var output = backend.pickPdfSaveAs("split.pdf")
                            if (output) {
                                page.busy = true
                                backend.splitPdf(page.splitFile, output, rangeField.text)
                            }
                        }
                    }
                }
            }
        }

        Controls.BusyIndicator {
            Layout.alignment: Qt.AlignHCenter
            running: page.busy
            visible: page.busy
        }
    }
}
