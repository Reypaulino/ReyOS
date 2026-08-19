import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Permissions"

    property bool busy: false

    Connections {
        target: backend
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
        }
        function onPathBrowsed(target, path) {
            if (path.length === 0) return
            if (target === "createField") createField.text = path
            else if (target === "folderField") folderField.text = path
            else if (target === "fileField") fileField.text = path
        }
    }

    function confirmAndFix(path, mode) {
        confirmDialog.pendingPath = path
        confirmDialog.pendingMode = mode
        confirmDialog.open()
    }

    Controls.Dialog {
        id: confirmDialog
        title: "Confirm folder change"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No

        property string pendingPath: ""
        property string pendingMode: ""

        onAccepted: {
            busy = true
            backend.fixFolderPermissions(pendingPath, pendingMode)
        }

        Controls.Label {
            wrapMode: Text.Wrap
            text: "This will recursively change ownership/permissions of:\n\n"
                  + confirmDialog.pendingPath
                  + "\n\nYou'll be asked for an admin password. Continue?"
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Create folder or file"; level: 3 }
                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Controls.TextField {
                        id: createField
                        Layout.fillWidth: true
                        placeholderText: "~/some/new/folder-or-file"
                    }
                    Controls.Button {
                        text: "Browse…"
                        enabled: !busy
                        onClicked: backend.browsePath("createField", true)
                    }
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Button {
                        text: "Create folder"
                        enabled: !busy && createField.text.length > 0
                        onClicked: { busy = true; backend.createPath(createField.text, true) }
                    }
                    Controls.Button {
                        text: "Create file"
                        enabled: !busy && createField.text.length > 0
                        onClicked: { busy = true; backend.createPath(createField.text, false) }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Fix folder permissions"; level: 3 }
                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Controls.TextField {
                        id: folderField
                        Layout.fillWidth: true
                        placeholderText: "~/some/folder"
                    }
                    Controls.Button {
                        text: "Browse…"
                        enabled: !busy
                        onClicked: backend.browsePath("folderField", true)
                    }
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Button {
                        text: "Grant write access"
                        enabled: !busy && folderField.text.length > 0
                        onClicked: confirmAndFix(folderField.text, "write")
                    }
                    Controls.Button {
                        text: "Take full ownership"
                        enabled: !busy && folderField.text.length > 0
                        onClicked: confirmAndFix(folderField.text, "own")
                    }
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.TextField {
                        id: chmodField
                        placeholderText: "chmod value, e.g. 755"
                        Layout.preferredWidth: 200
                    }
                    Controls.Button {
                        text: "Apply custom chmod"
                        enabled: !busy && folderField.text.length > 0 && chmodField.text.length > 0
                        onClicked: confirmAndFix(folderField.text, "custom:" + chmodField.text)
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    wrapMode: Text.Wrap
                    opacity: 0.75
                    font.pointSize: 9
                    text: "Common values — each digit is owner/group/others, read=4 write=2 execute=1:\n"
                        + "• 755 (rwxr-xr-x) — you: full access, everyone else: read/execute. Normal for folders and scripts.\n"
                        + "• 644 (rw-r--r--) — you: read/write, everyone else: read-only. Normal for regular files.\n"
                        + "• 700 (rwx------) — only you can access it at all. Good for private files/keys.\n"
                        + "• 777 (rwxrwxrwx) — everyone can read, write, and execute it. Avoid unless you specifically need it — any user on this system could modify or replace the file."
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Make file executable"; level: 3 }
                RowLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Controls.TextField {
                        id: fileField
                        Layout.fillWidth: true
                        placeholderText: "~/Downloads/some-script.sh"
                    }
                    Controls.Button {
                        text: "Browse…"
                        enabled: !busy
                        onClicked: backend.browsePath("fileField", false)
                    }
                }
                Controls.Button {
                    text: "chmod +x"
                    enabled: !busy && fileField.text.length > 0
                    onClicked: { busy = true; backend.makeExecutable(fileField.text) }
                }
            }
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: busy
            visible: busy
        }
    }
}
