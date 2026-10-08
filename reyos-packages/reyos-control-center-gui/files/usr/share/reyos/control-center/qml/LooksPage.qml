import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Looks"

    property var looks: []

    function reload() { looks = backend.looksInfo() }
    Component.onCompleted: reload()

    Connections {
        target: backend
        function onActionFinished(ok, message) {
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
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
            text: "A Look bundles a color palette, a wallpaper set, and the ReyOS keyboard scheme (Meta+1-9 for workspaces, Meta+Q to close, Meta+F for fullscreen). Applying one restarts the desktop shell."
        }

        Repeater {
            model: looks
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                padding: Kirigami.Units.gridUnit
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing

                    Rectangle {
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                        Layout.preferredHeight: Kirigami.Units.gridUnit * 2
                        radius: 6
                        color: modelData.background
                        border.color: modelData.accent
                        border.width: 2

                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width * 0.4
                            height: 8
                            radius: 4
                            color: modelData.accent
                        }
                    }

                    Controls.Label {
                        text: modelData.name
                        font.bold: true
                        Layout.fillWidth: true
                    }

                    Kirigami.Icon {
                        visible: modelData.active
                        source: "checkmark"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }

                    Controls.Button {
                        text: modelData.active ? "Applied" : "Apply"
                        enabled: !modelData.active
                        onClicked: backend.applyLook(modelData.id)
                    }
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
