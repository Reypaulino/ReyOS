import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Startup Apps"

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
        backend.listAutostart()
    }

    Connections {
        target: backend
        function onAutostartListed(list) {
            busy = false
            startupModel.clear()
            for (var i = 0; i < list.length; i++) startupModel.append(list[i])
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: startupModel }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

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
                Repeater {
                    model: startupModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label { text: name; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.Switch {
                            checked: isEnabled
                            enabled: !busy
                            onToggled: { busy = true; backend.setAutostartEnabled(file, checked) }
                        }
                    }
                }
                Controls.Label {
                    visible: startupModel.count === 0
                    text: "No autostart entries found."
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
