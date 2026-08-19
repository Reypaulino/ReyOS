import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Flatpak"

    property bool busy: false

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
            for (var i = 0; i < list.length; i++) appsModel.append(list[i])
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
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
                text: "Update all"
                highlighted: true
                enabled: !busy
                onClicked: { busy = true; backend.updateFlatpaks() }
            }
        }

        Controls.ProgressBar {
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
                Repeater {
                    model: appsModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label { text: appName; Layout.preferredWidth: 220; elide: Text.ElideRight }
                        Controls.Label { text: appVersion; opacity: 0.7; Layout.fillWidth: true; elide: Text.ElideRight }
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
