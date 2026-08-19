import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Sound"

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
        backend.refreshAudioInfo()
    }

    Connections {
        target: backend
        function onAudioInfoReady(info) {
            busy = false
            sinkModel.clear()
            for (var i = 0; i < info.sinks.length; i++) sinkModel.append(info.sinks[i])
            sourceModel.clear()
            for (var j = 0; j < info.sources.length; j++) sourceModel.append(info.sources[j])
        }
        function onActionFinished(ok, message) {
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: sinkModel }
    ListModel { id: sourceModel }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Output devices"; level: 3 }
                Repeater {
                    model: sinkModel
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: index > 0 ? Kirigami.Units.largeSpacing : 0
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Label { text: description; font.bold: isDefault; elide: Text.ElideRight; Layout.fillWidth: true }
                            Controls.Label { visible: isDefault; text: "default"; opacity: 0.6 }
                            Controls.Button {
                                text: "Set default"
                                visible: !isDefault
                                enabled: !busy
                                onClicked: { busy = true; backend.setDefaultSink(name) }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Slider {
                                Layout.fillWidth: true
                                from: 0; to: 150; stepSize: 1
                                value: volume
                                onPressedChanged: if (!pressed) backend.setSinkVolume(name, Math.round(value))
                            }
                            Controls.Label { text: volume + "%"; Layout.preferredWidth: 44 }
                            Controls.Button {
                                text: muted ? "Unmute" : "Mute"
                                enabled: !busy
                                onClicked: { busy = true; backend.setSinkMute(name, !muted) }
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: sinkModel.count === 0 && !busy
                    text: "No output devices found."
                    opacity: 0.7
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Input devices"; level: 3 }
                Repeater {
                    model: sourceModel
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: index > 0 ? Kirigami.Units.largeSpacing : 0
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Label { text: description; font.bold: isDefault; elide: Text.ElideRight; Layout.fillWidth: true }
                            Controls.Label { visible: isDefault; text: "default"; opacity: 0.6 }
                            Controls.Button {
                                text: "Set default"
                                visible: !isDefault
                                enabled: !busy
                                onClicked: { busy = true; backend.setDefaultSource(name) }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Slider {
                                Layout.fillWidth: true
                                from: 0; to: 150; stepSize: 1
                                value: volume
                                onPressedChanged: if (!pressed) backend.setSourceVolume(name, Math.round(value))
                            }
                            Controls.Label { text: volume + "%"; Layout.preferredWidth: 44 }
                            Controls.Button {
                                text: muted ? "Unmute" : "Mute"
                                enabled: !busy
                                onClicked: { busy = true; backend.setSourceMute(name, !muted) }
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: sourceModel.count === 0 && !busy
                    text: "No input devices found."
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
