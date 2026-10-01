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
    property var screenSleep: ({})

    readonly property var lockChoices: [
        { t: "Never", v: 0 }, { t: "After 5 minutes", v: 5 }, { t: "After 10 minutes", v: 10 },
        { t: "After 15 minutes", v: 15 }, { t: "After 30 minutes", v: 30 }, { t: "After 60 minutes", v: 60 } ]
    readonly property var dimChoices: [
        { t: "Never", v: 0 }, { t: "After 2 minutes", v: 2 }, { t: "After 5 minutes", v: 5 },
        { t: "After 10 minutes", v: 10 }, { t: "After 15 minutes", v: 15 } ]
    readonly property var offChoices: [
        { t: "Never", v: 0 }, { t: "After 2 minutes", v: 2 }, { t: "After 5 minutes", v: 5 },
        { t: "After 10 minutes", v: 10 }, { t: "After 15 minutes", v: 15 }, { t: "After 30 minutes", v: 30 } ]
    readonly property var sleepChoices: [
        { t: "Never", v: 0 }, { t: "After 10 minutes", v: 10 }, { t: "After 15 minutes", v: 15 },
        { t: "After 30 minutes", v: 30 }, { t: "After 60 minutes", v: 60 }, { t: "After 2 hours", v: 120 } ]
    readonly property var lidChoices: [
        { t: "Sleep", v: 1 }, { t: "Lock the screen", v: 32 }, { t: "Do nothing", v: 0 } ]

    // Index of the choice closest to the saved value (a value set elsewhere,
    // e.g. 7 minutes, still lands on a sensible entry instead of "Never").
    function choiceIndex(choices, value) {
        if (value === undefined) return 0
        var best = 0, bestDiff = 1e9
        for (var i = 0; i < choices.length; i++) {
            var d = Math.abs(choices[i].v - value)
            if (value === 0 ? choices[i].v === 0 : (choices[i].v !== 0 && d < bestDiff)) { best = i; bestDiff = d }
        }
        return best
    }

    Component.onCompleted: backend.refreshScreenSleep()

    Connections {
        target: backend
        function onScreenSleepReady(s) { screenSleep = s }
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
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
        }
    }

    Controls.Dialog {
        id: highPerformanceConfirm
        title: "Enable high performance?"
        modal: true
        width: 420
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: { busy = true; backend.performanceMode() }
        contentItem: Controls.Label {
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

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: Kirigami.FormLayout {
                Kirigami.Heading { Kirigami.FormData.isSection: true; text: "Screen & Sleep"; level: 3 }

                Controls.ComboBox {
                    id: lockBox
                    Kirigami.FormData.label: "Lock the screen:"
                    model: lockChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(lockChoices, screenSleep.lockMinutes)
                }
                Controls.CheckBox {
                    id: lockResumeBox
                    text: "Ask for my password when the computer wakes up"
                    checked: screenSleep.lockOnResume !== false
                }

                Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "When plugged in" }
                Controls.ComboBox {
                    id: acDimBox
                    Kirigami.FormData.label: "Dim the screen:"
                    model: dimChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(dimChoices, screenSleep.acDim)
                }
                Controls.ComboBox {
                    id: acOffBox
                    Kirigami.FormData.label: "Turn off the screen:"
                    model: offChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(offChoices, screenSleep.acScreenOff)
                }
                Controls.ComboBox {
                    id: acSleepBox
                    Kirigami.FormData.label: "Go to sleep:"
                    model: sleepChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(sleepChoices, screenSleep.acSleep)
                }
                Controls.ComboBox {
                    id: acLidBox
                    visible: screenSleep.hasBattery === true
                    Kirigami.FormData.label: "When the lid closes:"
                    model: lidChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(lidChoices, screenSleep.acLid)
                }

                Kirigami.Separator { visible: screenSleep.hasBattery === true; Kirigami.FormData.isSection: true; Kirigami.FormData.label: "On battery" }
                Controls.ComboBox {
                    id: batDimBox
                    visible: screenSleep.hasBattery === true
                    Kirigami.FormData.label: "Dim the screen:"
                    model: dimChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(dimChoices, screenSleep.batteryDim)
                }
                Controls.ComboBox {
                    id: batOffBox
                    visible: screenSleep.hasBattery === true
                    Kirigami.FormData.label: "Turn off the screen:"
                    model: offChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(offChoices, screenSleep.batteryScreenOff)
                }
                Controls.ComboBox {
                    id: batSleepBox
                    visible: screenSleep.hasBattery === true
                    Kirigami.FormData.label: "Go to sleep:"
                    model: sleepChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(sleepChoices, screenSleep.batterySleep)
                }
                Controls.ComboBox {
                    id: batLidBox
                    visible: screenSleep.hasBattery === true
                    Kirigami.FormData.label: "When the lid closes:"
                    model: lidChoices; textRole: "t"; valueRole: "v"
                    currentIndex: choiceIndex(lidChoices, screenSleep.batteryLid)
                }

                Controls.Button {
                    text: "Apply"
                    enabled: !busy
                    onClicked: {
                        busy = true
                        backend.applyScreenSleep({
                            lockMinutes: lockBox.currentValue, lockOnResume: lockResumeBox.checked,
                            acDim: acDimBox.currentValue, acScreenOff: acOffBox.currentValue, acSleep: acSleepBox.currentValue,
                            acLid: acLidBox.visible ? acLidBox.currentValue : (screenSleep.acLid === undefined ? 1 : screenSleep.acLid),
                            batteryDim: batDimBox.visible ? batDimBox.currentValue : (screenSleep.batteryDim === undefined ? 5 : screenSleep.batteryDim),
                            batteryScreenOff: batOffBox.visible ? batOffBox.currentValue : (screenSleep.batteryScreenOff || 0),
                            batterySleep: batSleepBox.visible ? batSleepBox.currentValue : (screenSleep.batterySleep || 0),
                            batteryLid: batLidBox.visible ? batLidBox.currentValue : (screenSleep.batteryLid === undefined ? 1 : screenSleep.batteryLid)
                        })
                    }
                }
            }
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: busy
            visible: busy
        }
    }
}
