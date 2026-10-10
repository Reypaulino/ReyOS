import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Flatpak"

    property bool busy: false
    property int updateCount: 0

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.listFlatpaks()
    }

    Connections {
        target: backend
        function onFlatpaksListed(list) {
            busy = false
            appsModel.clear()
            var updates = 0
            for (var i = 0; i < list.length; i++) {
                appsModel.append(list[i])
                if (list[i].hasUpdate) updates++
            }
            updateCount = updates
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: appsModel }

    Controls.Dialog {
        id: confirmRemove
        title: "Remove Flatpak app"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingId: ""
        property string pendingName: ""
        onAccepted: { busy = true; backend.removeFlatpak(pendingId) }
        Controls.Label {
            text: "Remove " + confirmRemove.pendingName + "?"
            wrapMode: Text.Wrap
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
                text: updateCount > 0 ? "Update all (" + updateCount + ")" : "Update all"
                highlighted: true
                enabled: !busy
                onClicked: { busy = true; backend.updateFlatpaks() }
            }
        }

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Installed Flatpak apps"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: busy && appsModel.count === 0 ? "Checking for updates..."
                        : updateCount === 1 ? "1 update available."
                        : updateCount > 1 ? updateCount + " updates available."
                        : "All apps are up to date."
                    color: updateCount > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.textColor
                    opacity: updateCount > 0 ? 1 : 0.7
                }
                Repeater {
                    model: appsModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label { text: appName; Layout.preferredWidth: 220; elide: Text.ElideRight }
                        Controls.Label {
                            text: hasUpdate ? appVersion + "  →  " + (updateVersion || "new build") : appVersion
                            opacity: hasUpdate ? 1 : 0.7
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Controls.Label {
                            visible: hasUpdate
                            text: "Update available"
                            color: Kirigami.Theme.positiveTextColor
                        }
                        Controls.Button {
                            text: "Remove"
                            enabled: !busy
                            onClicked: {
                                confirmRemove.pendingId = appId
                                confirmRemove.pendingName = appName
                                confirmRemove.open()
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: appsModel.count === 0
                    text: "No Flatpak apps installed."
                    opacity: 0.7
                }
            }
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
