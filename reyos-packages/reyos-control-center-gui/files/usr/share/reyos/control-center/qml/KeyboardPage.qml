import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Keyboard"

    property bool busy: false
    property var currentLayouts: []
    property var layoutNames: ({})
    property string switchShortcut: ""

    function refresh() {
        busy = true
        backend.refreshKeyboardInfo()
        backend.listCustomShortcuts()
    }

    Connections {
        target: backend
        function onKeyboardInfoReady(info) {
            busy = false
            currentLayouts = info.currentLayouts
            layoutModel.clear()
            layoutNames = info.layoutNames || {}
            var rows = info.availableLayouts.map(function (c) { return { code: c, label: (layoutNames[c] || c) } })
            rows.sort(function (a, b) { return a.label.localeCompare(b.label) })
            for (var i = 0; i < rows.length; i++) layoutModel.append(rows[i])
            for (var j = 0; j < layoutModel.count; j++)
                if (currentLayouts.length > 0 && layoutModel.get(j).code === currentLayouts[0]) layoutBox.currentIndex = j
            rateSlider.value = info.repeatRate
            delaySlider.value = info.repeatDelay

            switchShortcutModel.clear()
            var selectIndex = 0
            for (var j = 0; j < info.switchShortcutOptions.length; j++) {
                switchShortcutModel.append(info.switchShortcutOptions[j])
                if (info.switchShortcutOptions[j].value === info.switchShortcut) selectIndex = j
            }
            switchShortcut = info.switchShortcut
            switchShortcutBox.currentIndex = selectIndex
        }
        function onCustomShortcutsListed(list) {
            shortcutModel.clear()
            for (var k = 0; k < list.length; k++) shortcutModel.append(list[k])
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: layoutModel }
    ListModel { id: switchShortcutModel }
    ListModel { id: shortcutModel }

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
                Kirigami.Heading { text: "Layout"; level: 3 }
                Controls.Label {
                    text: "Now: " + currentLayouts.map(function (c) { return layoutNames[c] || c }).join(", ")
                    visible: currentLayouts.length > 0
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.ComboBox {
                        id: layoutBox
                        Layout.fillWidth: true
                        model: layoutModel
                        textRole: "label"
                    }
                    Controls.Button {
                        text: "Use this layout"
                        enabled: !busy && layoutBox.currentIndex >= 0
                        onClicked: { busy = true; backend.setKeyboardLayouts([layoutModel.get(layoutBox.currentIndex).code]) }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    font.pointSize: 9
                    text: "The new layout starts the next time you log in."
                }

                Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.smallSpacing }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label { text: "Switch layout:" }
                    Controls.ComboBox {
                        id: switchShortcutBox
                        Layout.fillWidth: true
                        model: switchShortcutModel
                        textRole: "label"
                        enabled: !busy
                        onActivated: {
                            busy = true
                            backend.setLayoutSwitchShortcut(switchShortcutModel.get(currentIndex).value)
                        }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: Kirigami.FormLayout {
                RowLayout {
                    Kirigami.FormData.label: "Repeat rate:"
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Slider {
                        id: rateSlider
                        from: 2; to: 60; stepSize: 1
                    }
                    Controls.Label { text: Math.round(rateSlider.value) + " / s" }
                }
                RowLayout {
                    Kirigami.FormData.label: "Repeat delay:"
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Slider {
                        id: delaySlider
                        from: 100; to: 2000; stepSize: 50
                    }
                    Controls.Label { text: Math.round(delaySlider.value) + " ms" }
                }
                Controls.Button {
                    text: "Apply"
                    enabled: !busy
                    onClicked: {
                        busy = true
                        backend.setKeyRepeat(Math.round(rateSlider.value), Math.round(delaySlider.value))
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Custom Shortcuts"; level: 3 }

                Repeater {
                    model: shortcutModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Label { text: keys; font.bold: true; Layout.preferredWidth: Kirigami.Units.gridUnit * 8; elide: Text.ElideRight }
                        Controls.Label { text: command; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.ToolButton {
                            icon.name: "edit-delete"
                            enabled: !busy
                            onClicked: { busy = true; backend.removeCustomShortcut(index) }
                        }
                    }
                }

                Controls.Label {
                    visible: shortcutModel.count === 0
                    text: "No custom shortcuts yet."
                    opacity: 0.7
                }

                Kirigami.Separator { Layout.fillWidth: true }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.TextField {
                        id: newKeysField
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 8
                        placeholderText: "e.g. Mod4 + t"
                    }
                    Controls.TextField {
                        id: newCommandField
                        Layout.fillWidth: true
                        placeholderText: "Command to run, e.g. konsole"
                    }
                    Controls.Button {
                        text: "Add"
                        enabled: !busy && newKeysField.text.length > 0 && newCommandField.text.length > 0
                        onClicked: {
                            busy = true
                            backend.addCustomShortcut(newKeysField.text, newCommandField.text)
                            newKeysField.text = ""
                            newCommandField.text = ""
                        }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    font.pointSize: 9
                    text: "Modifiers: control, shift, alt, Mod4 (Win/Super) — combine with \"+\", e.g. \"control+shift + Return\". Applies immediately."
                }
            }
        }

        ReyOSProgressBar {
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
