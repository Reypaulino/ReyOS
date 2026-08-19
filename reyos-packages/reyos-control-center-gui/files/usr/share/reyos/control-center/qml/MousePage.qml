import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Mouse"

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
        backend.refreshMouseInfo()
    }

    Connections {
        target: backend
        function onMouseInfoReady(info) {
            busy = false
            deviceModel.clear()
            for (var i = 0; i < info.devices.length; i++) deviceModel.append(info.devices[i])
        }
        function onActionFinished(ok, message) {
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: deviceModel }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Repeater {
            model: deviceModel
            delegate: Kirigami.AbstractCard {
                Layout.fillWidth: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: name; level: 3 }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Label { text: "Pointer speed:" }
                        Controls.Slider {
                            id: speedSlider
                            Layout.fillWidth: true
                            from: -1; to: 1; stepSize: 0.05
                            value: pointerAcceleration
                            onPressedChanged: if (!pressed) backend.setMousePointerAcceleration(vendor, product, name, value)
                        }
                        Controls.Label { text: speedSlider.value.toFixed(2); Layout.preferredWidth: 40 }
                    }

                    Controls.CheckBox {
                        text: "Left-handed (swap buttons)"
                        checked: leftHanded
                        enabled: !busy
                        onToggled: backend.setMouseLeftHanded(vendor, product, name, checked)
                    }
                    Controls.CheckBox {
                        text: "Natural scrolling"
                        checked: naturalScroll
                        enabled: !busy
                        onToggled: backend.setMouseNaturalScroll(vendor, product, name, checked)
                    }
                }
            }
        }

        Controls.Label {
            visible: deviceModel.count === 0 && !busy
            text: "No pointer devices found."
            opacity: 0.7
        }

        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            font.pointSize: 9
            text: "Changes apply immediately on this session (via xinput) and are saved for next login too. If a device doesn't support live apply, the setting still takes effect at next login."
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
