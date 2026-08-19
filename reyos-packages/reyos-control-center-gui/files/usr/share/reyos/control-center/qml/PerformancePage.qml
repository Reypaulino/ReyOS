import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Power & Performance"

    property string governor: "N/A"
    property int swappiness: 50
    property string swapStatus: "OFF"
    property bool busy: false
    property string cpuUsage: "—"
    property string memoryUsage: "—"
    property string swapUsage: "—"
    property string systemUptime: "—"

    Connections {
        target: backend
        function onStatsUpdated(s) {
            if (!swapSlider.pressed) swapSlider.value = s.swappiness
            governor = s.governor
            swapStatus = s.swapStatus
            cpuUsage = s.cpu + "%"
            memoryUsage = s.memUsed + " MiB of " + s.memTotal + " MiB"
            swapUsage = s.swapUsed + " MiB of " + s.swapTotal + " MiB"
            systemUptime = s.uptime
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
        }
    }

    Controls.Dialog {
        id: highPerformanceConfirm
        title: "Enable high performance?"
        modal: true
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: { busy = true; backend.performanceMode() }
        contentItem: Controls.Label {
            width: 360
            wrapMode: Text.Wrap
            text: "This favors responsiveness for games and demanding work. It can use more power, produce more heat, and reduce battery life. You can change the governor and swappiness below at any time."
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
                Kirigami.Heading { text: "System activity"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "CPU: " + cpuUsage + "    Memory: " + memoryUsage + "    Swap: " + swapUsage + "    Uptime: " + systemUptime
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.75
                    text: "Linux uses free RAM as cache and releases it automatically when apps need it. No manual RAM cleaning is needed."
                }
                Controls.Button {
                    text: "Enable high performance"
                    highlighted: true
                    enabled: !busy
                    onClicked: highPerformanceConfirm.open()
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: Kirigami.FormLayout {
                Controls.Label { Kirigami.FormData.label: "Current governor:"; text: governor }

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.FormData.label: "Set governor:"
                    Controls.ComboBox {
                        id: govBox
                        model: ["performance", "ondemand", "powersave"]
                    }
                    Controls.Button {
                        text: "Apply"
                        enabled: !busy
                        onClicked: { busy = true; backend.setGovernor(govBox.currentText) }
                    }
                }

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.FormData.label: "Swappiness:"
                    Controls.Slider {
                        id: swapSlider
                        from: 0; to: 100; stepSize: 1
                        value: swappiness
                    }
                    Controls.Label { text: Math.round(swapSlider.value) }
                    Controls.Button {
                        text: "Apply"
                        enabled: !busy
                        onClicked: { busy = true; backend.setSwappiness(Math.round(swapSlider.value)) }
                    }
                }

                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.FormData.label: "Swap:"
                    Controls.Label { text: swapStatus }
                    Controls.Button {
                        text: swapStatus === "ON" ? "Disable swap" : "Enable swap"
                        enabled: !busy
                        onClicked: { busy = true; backend.toggleSwap() }
                    }
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
