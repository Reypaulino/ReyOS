import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Default Apps"

    property var categories: []

    function reload() { categories = backend.defaultAppsInfo() }
    Component.onCompleted: reload()

    Connections {
        target: backend
        function onActionFinished(ok, message) {
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            reload()
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: "Choose which app opens each type of file by default."
        }

        Repeater {
            model: categories
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                padding: Kirigami.Units.gridUnit
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label {
                        text: modelData.label
                        font.bold: true
                        Layout.preferredWidth: 170
                    }
                    Controls.ComboBox {
                        Layout.fillWidth: true
                        model: modelData.options
                        textRole: "name"
                        currentIndex: {
                            for (var i = 0; i < modelData.options.length; i++)
                                if (modelData.options[i].desktopId === modelData.currentId) return i
                            return -1
                        }
                        displayText: currentIndex === -1 ? modelData.currentName : currentText
                        onActivated: backend.setDefaultApp(modelData.mimetypesCsv, modelData.options[currentIndex].desktopId)
                    }
                }
            }
        }

        Controls.Label {
            visible: categories.length === 0
            Layout.fillWidth: true
            text: "No candidate apps found for any category."
            opacity: 0.7
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
