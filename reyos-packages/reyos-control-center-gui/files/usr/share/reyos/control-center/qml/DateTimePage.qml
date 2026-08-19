import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Date & Time"

    property bool busy: false
    property bool ntpEnabled: false
    property string currentTimezone: "…"
    property string clockFormat: "default"

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshDateTimeInfo()
    }

    Connections {
        target: backend
        function onDatetimeInfoReady(info) {
            busy = false
            currentTimezone = info.timezone
            ntpEnabled = info.ntp
            localTimeLabel.text = info.localTime
            syncedLabel.text = info.synced ? "Synchronized" : "Not synchronized"
            clockFormat = info.clockFormat
            clockFormatBox.currentIndex = clockFormatBox.indexOfValue(info.clockFormat)
        }
        function onTimezonesListed(list) {
            tzModel.clear()
            for (var i = 0; i < list.length; i++) tzModel.append({ tz: list[i] })
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: { refresh(); backend.listTimezones() }

    ListModel { id: tzModel }

    Controls.Dialog {
        id: tzDialog
        title: "Choose timezone"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        // appWindow (Main.qml's id) isn't reachable here -- this page is
        // loaded as its own separate document via pageStack, with its own
        // id namespace, not Main.qml's. Overlay.overlay is the
        // cross-document-safe way to size/center against the window.
        width: Math.min(500, Controls.Overlay.overlay.width - Kirigami.Units.gridUnit * 4)
        height: Math.min(500, Controls.Overlay.overlay.height - Kirigami.Units.gridUnit * 4)
        standardButtons: Controls.Dialog.Cancel

        ColumnLayout {
            anchors.fill: parent
            Controls.TextField {
                id: tzSearchField
                Layout.fillWidth: true
                placeholderText: "Search timezones…"
            }
            Controls.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ListView {
                    model: tzModel
                    delegate: Controls.ItemDelegate {
                        width: ListView.view.width
                        text: tz
                        visible: tzSearchField.text.length === 0 || tz.toLowerCase().includes(tzSearchField.text.toLowerCase())
                        height: visible ? implicitHeight : 0
                        onClicked: {
                            busy = true
                            backend.setTimezone(tz)
                            tzDialog.close()
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

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: Kirigami.FormLayout {
                Controls.Label { id: localTimeLabel; Kirigami.FormData.label: "Current time:" }
                Controls.Label { id: syncedLabel; Kirigami.FormData.label: "NTP status:" }
                RowLayout {
                    Kirigami.FormData.label: "Timezone:"
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label { text: currentTimezone }
                    Controls.Button {
                        text: "Change…"
                        enabled: !busy
                        onClicked: tzDialog.open()
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: RowLayout {
                spacing: Kirigami.Units.largeSpacing
                Controls.Label { text: "Clock format:" }
                Controls.ComboBox {
                    id: clockFormatBox
                    Layout.fillWidth: true
                    textRole: "label"
                    valueRole: "value"
                    model: [
                        { value: "default", label: "Regional default" },
                        { value: "12h", label: "12-hour (3:45 PM)" },
                        { value: "24h", label: "24-hour (15:45)" }
                    ]
                    enabled: !busy
                    onActivated: { busy = true; backend.setClockFormat(currentValue) }
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
                    Kirigami.Heading { text: "Automatic date & time"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Switch {
                        checked: ntpEnabled
                        enabled: !busy
                        onToggled: { busy = true; backend.setNtpEnabled(checked) }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    visible: !ntpEnabled
                    Controls.TextField {
                        id: manualField
                        Layout.fillWidth: true
                        placeholderText: "YYYY-MM-DD HH:MM:SS"
                    }
                    Controls.Button {
                        text: "Set"
                        enabled: !busy && manualField.text.length > 0
                        onClicked: { busy = true; backend.setManualDateTime(manualField.text) }
                    }
                }
            }
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
