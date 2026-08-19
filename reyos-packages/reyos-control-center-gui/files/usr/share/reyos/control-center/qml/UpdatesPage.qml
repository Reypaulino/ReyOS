import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Updates"

    property bool running: false

    Connections {
        target: backend
        function onPkgProgress(line) {
            logArea.append(line)
        }
        function onPkgFinished(ok, message) {
            running = false
            logArea.append(ok ? "\n✓ " + message : "\n✗ " + message)
        }
        function onOrphansListed(list) {
            orphansLabel.text = list.length > 0
                ? list.length + " orphaned package(s): " + list.join(", ")
                : "No orphaned packages."
        }
        function onPackagesFound(list) {
            pkgModel.clear()
            for (var i = 0; i < list.length; i++) pkgModel.append(list[i])
        }
        function onActionFinished(ok, message) {
            running = false
            pkgStatusLabel.text = message
            pkgStatusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) backend.searchPackages(pkgSearchField.text)
        }
        function onPackageInfoReady(name, info) {
            pkgInfoDialog.pendingName = name
            pkgInfoText.text = info
            pkgInfoDialog.open()
        }
    }

    ListModel { id: pkgModel }

    Controls.Dialog {
        id: confirmRemovePkg
        title: "Remove package"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingName: ""
        onAccepted: { running = true; backend.removePackage(pendingName) }
        Controls.Label {
            text: "Remove " + confirmRemovePkg.pendingName + "? This may also remove packages that depend on it."
            wrapMode: Text.Wrap
        }
    }

    Controls.Dialog {
        id: pkgInfoDialog
        title: "Package: " + pendingName
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        width: Math.min(parent ? parent.width * 0.8 : 600, 700)
        height: Math.min(parent ? parent.height * 0.8 : 500, 560)
        property string pendingName: ""

        footer: Controls.DialogButtonBox {
            Controls.Button {
                text: "Remove"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.DestructiveRole
                onClicked: {
                    pkgInfoDialog.close()
                    confirmRemovePkg.pendingName = pkgInfoDialog.pendingName
                    confirmRemovePkg.open()
                }
            }
            Controls.Button {
                text: "Close"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.RejectRole
                onClicked: pkgInfoDialog.close()
            }
        }

        Controls.ScrollView {
            anchors.fill: parent
            Controls.TextArea {
                id: pkgInfoText
                readOnly: true
                wrapMode: TextEdit.Wrap
                font.family: "monospace"
                font.pointSize: 9
            }
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            Controls.Button {
                text: "Check for updates"
                enabled: !running
                onClicked: { running = true; logArea.text = ""; backend.runPkgAction("check") }
            }
            Controls.Button {
                text: "Install updates"
                enabled: !running
                onClicked: { running = true; logArea.text = ""; backend.runPkgAction("upgrade") }
            }
            Controls.Button {
                text: "Full update"
                highlighted: true
                enabled: !running
                onClicked: { running = true; logArea.text = ""; backend.runPkgAction("full") }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing

            Controls.Button {
                text: "List orphaned packages"
                enabled: !running
                onClicked: backend.listOrphans()
            }
            Controls.Button {
                text: "Remove orphans + clean cache"
                enabled: !running
                onClicked: { running = true; logArea.text = ""; backend.runPkgAction("clean") }
            }
        }

        Controls.Label {
            id: orphansLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            visible: text.length > 0
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Installed packages"; level: 3 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.TextField {
                        id: pkgSearchField
                        Layout.fillWidth: true
                        placeholderText: "Search installed packages, e.g. reyos-browser"
                        enabled: !running
                        onAccepted: backend.searchPackages(text)
                    }
                    Controls.Button {
                        text: "Search"
                        enabled: !running && pkgSearchField.text.length > 0
                        onClicked: backend.searchPackages(pkgSearchField.text)
                    }
                }
                Repeater {
                    model: pkgModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label { text: name; Layout.preferredWidth: 220; elide: Text.ElideRight }
                        Controls.Label { text: version; opacity: 0.7; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.Button {
                            text: "Info"
                            enabled: !running
                            onClicked: backend.getPackageInfo(name)
                        }
                        Controls.Button {
                            text: "Remove"
                            enabled: !running
                            onClicked: { confirmRemovePkg.pendingName = name; confirmRemovePkg.open() }
                        }
                    }
                }
                Controls.Label {
                    visible: pkgModel.count === 0 && pkgSearchField.text.length > 0
                    text: "No matches."
                    opacity: 0.7
                }
                Controls.Label {
                    id: pkgStatusLabel
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                }
            }
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: running
            visible: running
        }

        Controls.ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 320
            Controls.TextArea {
                id: logArea
                readOnly: true
                wrapMode: TextEdit.Wrap
                font.family: "monospace"
                font.pointSize: 9
                function append(line) {
                    text += line + "\n"
                    cursorPosition = text.length
                }
            }
        }
    }
}
