import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Startup Apps"

    property bool busy: false
    property string filter: ""

    actions: [
        Kirigami.Action {
            text: "Add App…"
            icon.name: "list-add"
            enabled: !busy
            onTriggered: {
                candidatesModel.clear()
                addDialog.loading = true
                searchField.text = ""
                addDialog.open()
                backend.listStartupCandidates()
            }
        },
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        restoreSwitch.checked = backend.sessionRestoreEnabled()
        backend.listAutostart()
    }

    Connections {
        target: backend
        function onAutostartListed(list) {
            busy = false
            startupModel.clear()
            for (var i = 0; i < list.length; i++) startupModel.append(list[i])
        }
        function onStartupCandidatesListed(list) {
            addDialog.loading = false
            candidatesModel.clear()
            for (var i = 0; i < list.length; i++) candidatesModel.append(list[i])
        }
        function onActionFinished(ok, message) {
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
            refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: startupModel }
    ListModel { id: candidatesModel }

    Controls.Dialog {
        id: addDialog
        title: "Start an app when you log in"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        width: Math.min(page.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 26)
        height: Math.min(page.height - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 28)
        standardButtons: Controls.Dialog.Close
        property bool loading: false

        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            Kirigami.SearchField {
                id: searchField
                Layout.fillWidth: true
                onTextChanged: page.filter = text.toLowerCase()
            }
            ReyOSProgressBar {
                Layout.fillWidth: true
                indeterminate: true
                visible: addDialog.loading
            }
            Controls.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ListView {
                    model: candidatesModel
                    delegate: Controls.ItemDelegate {
                        width: ListView.view.width
                        visible: page.filter === "" || model.name.toLowerCase().indexOf(page.filter) >= 0
                        height: visible ? implicitHeight : 0
                        contentItem: RowLayout {
                            spacing: Kirigami.Units.largeSpacing
                            Kirigami.Icon {
                                source: model.icon || "application-x-executable"
                                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                            }
                            Controls.Label { text: model.name; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                        onClicked: {
                            addDialog.close()
                            busy = true
                            backend.addAutostart(model.id)
                        }
                    }
                }
            }
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: RowLayout {
                spacing: Kirigami.Units.largeSpacing
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Controls.Label { text: "Reopen apps from last session"; font.bold: true }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.75
                        text: "Apps that were open when you logged out or shut down open again at your next login. Turn off to start with an empty desktop."
                    }
                }
                Controls.Switch {
                    id: restoreSwitch
                    enabled: !busy
                    onToggled: { busy = true; backend.setSessionRestore(checked) }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Label { text: "Start when you log in"; font.bold: true; Layout.fillWidth: true }
                    Controls.Button {
                        text: "Add App…"
                        icon.name: "list-add"
                        enabled: !busy
                        onClicked: page.actions[0].trigger()
                    }
                }
                Repeater {
                    model: startupModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Kirigami.Icon {
                            source: model.icon || "application-x-executable"
                            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                            Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                            opacity: model.isEnabled ? 1 : 0.5
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.Label { text: model.name; Layout.fillWidth: true; elide: Text.ElideRight }
                            Controls.Label {
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                                opacity: 0.65
                                font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.85
                                text: (model.builtin ? "Part of ReyOS" : (model.system ? "Comes with the system" : "Added by you")) + (model.comment ? " · " + model.comment : "")
                            }
                        }
                        Controls.Button {
                            visible: !model.system && !model.builtin
                            text: "Remove"
                            enabled: !busy
                            onClicked: { busy = true; backend.removeAutostart(model.id) }
                        }
                        Controls.Switch {
                            checked: model.isEnabled
                            enabled: !busy
                            onToggled: { busy = true; backend.setAutostartEnabled(model.id, checked) }
                        }
                    }
                }
                Controls.Label {
                    visible: startupModel.count === 0 && !busy
                    text: "Nothing starts automatically yet."
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
