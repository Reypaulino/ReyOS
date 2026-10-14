import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Chrome-style print preview over the browser window: pages on the left,
// settings on the right. The tab is rendered with WebEngineView.printToPdf()
// into a temp file (again whenever paper size or layout change); the backend
// draws previews from it and prints or saves it.
Rectangle {
    id: preview
    property var theme
    property var view: null
    property string title: ""
    property string jobPath: ""
    property bool busy: false
    property bool pendingRender: false
    property int generation: 0
    property int pageCount: 0
    property real pageAspect: 1.294
    property var destinations: []
    property var papers: []
    property string errorText: ""

    readonly property bool saving: destinationPicker.currentIndex === destinations.length
    readonly property bool customPages: pagesPicker.currentIndex === 1
    readonly property string pageSpec: customPages ? pagesField.text : ""
    // 1-based page numbers to print; empty while the custom range is invalid.
    readonly property var selected: browserBackend.selectedPages(pageSpec, pageCount)
    readonly property string rangeError: customPages && pageCount > 0 && selected.length === 0 ? "Enter pages like 1-3, 5 (this page has " + pageCount + ")." : ""
    readonly property int sheets: {
        const perCopy = twoSidedSwitch.checked && !saving ? Math.ceil(selected.length / 2) : selected.length
        return perCopy * (saving ? 1 : copiesBox.value)
    }

    visible: false
    color: Qt.rgba(0, 0, 0, 0.55)
    focus: visible

    function open(targetView, mode) {
        if (!targetView || visible) {
            return
        }
        view = targetView
        title = targetView.title || "Page"
        destinations = browserBackend.printDestinations()
        papers = browserBackend.paperSizes()
        const defaultPaper = browserBackend.printPageSizeId()
        let paperIndex = 0
        for (let i = 0; i < papers.length; ++i) {
            if (papers[i].id === defaultPaper) {
                paperIndex = i
            }
        }
        paperPicker.currentIndex = paperIndex
        destinationPicker.currentIndex = mode === "save" || destinations.length === 0 ? destinations.length : 0
        pagesPicker.currentIndex = 0
        pagesField.text = ""
        copiesBox.value = 1
        layoutPicker.currentIndex = 0
        colorPicker.currentIndex = 0
        twoSidedSwitch.checked = false
        errorText = ""
        pageCount = 0
        visible = true
        forceActiveFocus()
        render()
    }

    function close() {
        visible = false
        if (jobPath.length) {
            browserBackend.discardPrintFile(jobPath)
        }
        jobPath = ""
        busy = false
        pendingRender = false
        view = null
    }

    function render() {
        if (!view) {
            return
        }
        if (busy) {
            pendingRender = true
            return
        }
        busy = true
        if (jobPath.length) {
            browserBackend.discardPrintFile(jobPath)
        }
        jobPath = browserBackend.newPrintFile()
        view.printToPdf(jobPath, papers.length ? papers[paperPicker.currentIndex].id : browserBackend.printPageSizeId(), layoutPicker.currentIndex)
    }

    // Called by Main.qml for every WebEngineView.pdfPrintingFinished.
    function pdfReady(filePath, success) {
        if (!visible || filePath !== jobPath) {
            return false
        }
        busy = false
        if (pendingRender) {
            pendingRender = false
            render()
            return true
        }
        if (!success) {
            errorText = "This page couldn't be prepared for printing."
            pageCount = 0
            return true
        }
        const info = browserBackend.loadPrintPreview(filePath)
        pageCount = info.pages
        pageAspect = info.aspect
        errorText = ""
        generation += 1
        return true
    }

    function submit() {
        if (busy || pageCount === 0 || selected.length === 0) {
            return
        }
        let result
        if (saving) {
            result = browserBackend.savePreviewAsPdf(jobPath, title, pageSpec)
            if (result === "cancelled") {
                return
            }
        } else {
            result = browserBackend.printFromPreview(jobPath, title, destinations[destinationPicker.currentIndex].name, pageSpec,
                                                     copiesBox.value, colorPicker.currentIndex === 0, twoSidedSwitch.checked,
                                                     papers[paperPicker.currentIndex].id, layoutPicker.currentIndex === 1)
        }
        if (result.length) {
            errorText = result
        } else {
            close()
        }
    }

    Keys.onEscapePressed: close()

    // Swallow clicks/wheel so the page underneath doesn't react.
    MouseArea { anchors.fill: parent; hoverEnabled: true; onWheel: function(wheel) { wheel.accepted = true } }

    component FieldLabel: Label { color: "#D7C1AA"; font.pixelSize: 13; Layout.topMargin: 6 }

    component ThemedCombo: ComboBox {
        id: combo
        Layout.fillWidth: true
        contentItem: Text {
            leftPadding: 10
            rightPadding: combo.indicator.width + 10
            text: combo.displayText
            color: "#FFF3E6"
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle { implicitHeight: 34; color: preview.theme.base; border.color: combo.activeFocus ? preview.theme.accent : preview.theme.border; radius: 7 }
        popup: Popup {
            y: combo.height - 1
            width: combo.width
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 300)
            padding: 4
            background: Rectangle { color: preview.theme.raised; border.color: preview.theme.border; radius: 7 }
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                ScrollBar.vertical: ScrollBar {}
            }
        }
        delegate: ItemDelegate {
            required property int index
            required property var modelData
            width: combo.width - 8
            height: 34
            highlighted: combo.highlightedIndex === index
            contentItem: Text {
                text: combo.textRole ? modelData[combo.textRole] : modelData
                color: "#FFF3E6"
                verticalAlignment: Text.AlignVCenter
                leftPadding: 8
                elide: Text.ElideRight
            }
            background: Rectangle { color: highlighted ? preview.theme.hover : "transparent"; radius: 5 }
        }
    }

    component ThemedButton: Button {
        id: themedButton
        property bool primary: false
        contentItem: Text {
            text: themedButton.text
            color: themedButton.enabled ? (themedButton.primary ? "#1B130C" : "#FFF3E6") : "#9F8873"
            font.bold: themedButton.primary
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            implicitHeight: 36
            implicitWidth: 96
            radius: 8
            color: themedButton.primary
                   ? (themedButton.enabled ? (themedButton.hovered ? preview.theme.glow : preview.theme.accent) : preview.theme.hover)
                   : (themedButton.hovered ? preview.theme.hover : preview.theme.raised)
            border.color: themedButton.primary ? "transparent" : preview.theme.border
        }
    }

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: Math.min(1060, parent.width - 40)
        height: parent.height - 40
        radius: 12
        color: preview.theme.raised
        border.color: preview.theme.border
        clip: true

        RowLayout {
            anchors.fill: parent
            spacing: 0

            // Pages
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: preview.theme.windowBg
                radius: 12

                ListView {
                    id: pageList
                    anchors.fill: parent
                    anchors.margins: 18
                    clip: true
                    spacing: 18
                    model: preview.pageCount
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    delegate: Item {
                        required property int index
                        readonly property bool included: preview.selected.indexOf(index + 1) !== -1
                        width: pageList.width
                        height: pageImage.height + 24
                        Rectangle {
                            anchors.fill: pageImage
                            anchors.margins: -1
                            color: "white"
                            border.color: Qt.rgba(0, 0, 0, 0.4)
                        }
                        Image {
                            id: pageImage
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: Math.min(pageList.width - 24, 620)
                            height: width * preview.pageAspect
                            asynchronous: true
                            cache: false
                            sourceSize.width: Math.round(width * 1.5)
                            source: "image://reyvaprint/" + preview.generation + "/" + index
                            opacity: included ? 1.0 : 0.35
                        }
                        BusyIndicator { anchors.centerIn: pageImage; running: pageImage.status === Image.Loading; width: 36; height: 36 }
                        Label {
                            anchors.top: pageImage.bottom
                            anchors.topMargin: 4
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "Page " + (index + 1) + " of " + preview.pageCount
                            color: "#9F8873"
                            font.pixelSize: 12
                        }
                    }
                }
                ColumnLayout {
                    anchors.centerIn: parent
                    visible: preview.busy || preview.pageCount === 0
                    spacing: 10
                    BusyIndicator { Layout.alignment: Qt.AlignHCenter; running: preview.busy }
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: preview.busy ? "Preparing preview…" : preview.errorText
                        color: "#D7C1AA"
                    }
                }
            }

            // Settings
            Rectangle {
                Layout.preferredWidth: 320
                Layout.fillHeight: true
                color: preview.theme.raised
                radius: 12

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 4

                    Label { text: preview.saving ? "Save as PDF" : "Print"; font.bold: true; font.pixelSize: 22; color: "#FFF3E6" }
                    Label {
                        text: preview.busy || preview.pageCount === 0 ? " "
                              : preview.saving ? preview.selected.length + (preview.selected.length === 1 ? " page" : " pages")
                              : preview.sheets + (preview.sheets === 1 ? " sheet of paper" : " sheets of paper")
                        color: "#F4D5A8"
                        Layout.bottomMargin: 6
                    }

                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentHeight: fields.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        ColumnLayout {
                            id: fields
                            width: parent.width
                            spacing: 4

                            FieldLabel { text: "Destination" }
                            ThemedCombo {
                                id: destinationPicker
                                textRole: "label"
                                model: preview.destinations.concat([{ name: "", label: "Save as PDF" }])
                            }

                            FieldLabel { text: "Pages" }
                            ThemedCombo {
                                id: pagesPicker
                                model: ["All", "Custom"]
                                onActivated: {
                                    if (currentIndex === 1) {
                                        pagesField.forceActiveFocus()
                                    }
                                }
                            }
                            TextField {
                                id: pagesField
                                visible: preview.customPages
                                Layout.fillWidth: true
                                placeholderText: "e.g. 1-3, 5"
                                color: "#FFF3E6"
                                placeholderTextColor: "#8C7867"
                                selectByMouse: true
                                background: Rectangle { implicitHeight: 34; color: preview.theme.base; border.color: pagesField.activeFocus ? preview.theme.accent : preview.theme.border; radius: 7 }
                                onAccepted: preview.submit()
                            }

                            FieldLabel { text: "Copies"; visible: !preview.saving }
                            SpinBox {
                                id: copiesBox
                                visible: !preview.saving
                                from: 1
                                to: 99
                                editable: true
                                Layout.fillWidth: true
                            }

                            FieldLabel { text: "Layout" }
                            ThemedCombo {
                                id: layoutPicker
                                model: ["Portrait", "Landscape"]
                                onActivated: preview.render()
                            }

                            FieldLabel { text: "Paper size" }
                            ThemedCombo {
                                id: paperPicker
                                textRole: "name"
                                model: preview.papers
                                onActivated: preview.render()
                            }

                            FieldLabel { text: "Color"; visible: !preview.saving }
                            ThemedCombo {
                                id: colorPicker
                                visible: !preview.saving
                                model: ["Color", "Black and white"]
                            }

                            Switch {
                                id: twoSidedSwitch
                                visible: !preview.saving
                                text: "Print on both sides"
                                Layout.topMargin: 6
                                contentItem: Text { text: twoSidedSwitch.text; color: "#FFF3E6"; verticalAlignment: Text.AlignVCenter; leftPadding: twoSidedSwitch.indicator.width + 8 }
                            }

                            Label {
                                visible: !preview.saving
                                Layout.topMargin: 10
                                text: "<a href='more'>More settings (system print dialog)…</a>"
                                textFormat: Text.StyledText
                                linkColor: preview.theme.glow
                                color: preview.theme.glow
                                onLinkActivated: {
                                    const path = preview.jobPath
                                    const pageTitle = preview.title
                                    if (preview.busy || !path.length) {
                                        return
                                    }
                                    browserBackend.printWithSystemDialog(path, pageTitle)
                                    preview.close()
                                }
                                MouseArea { anchors.fill: parent; acceptedButtons: Qt.NoButton; cursorShape: Qt.PointingHandCursor }
                            }
                        }
                    }

                    Label {
                        visible: text.length > 0 && preview.pageCount > 0
                        text: preview.errorText.length ? preview.errorText : preview.rangeError
                        color: preview.theme.glow
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                        spacing: 10
                        Item { Layout.fillWidth: true }
                        ThemedButton { text: "Cancel"; onClicked: preview.close() }
                        ThemedButton {
                            primary: true
                            text: preview.saving ? "Save" : "Print"
                            enabled: !preview.busy && preview.pageCount > 0 && preview.selected.length > 0
                            onClicked: preview.submit()
                        }
                    }
                }
            }
        }
    }
}
