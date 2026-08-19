import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Services"

    property bool busy: false
    // Whether the current results came from a name search or the default
    // "what's running" view -- decides what a post-action refresh re-runs.
    property bool viewingSearch: false

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: viewingSearch ? search() : showRunning()
        }
    ]

    function showRunning() {
        viewingSearch = false
        busy = true
        backend.listRunningServices()
    }

    function search() {
        if (searchField.text.length === 0) return
        viewingSearch = true
        busy = true
        backend.searchServices(searchField.text)
    }

    Connections {
        target: backend
        function onServicesFound(list) {
            busy = false
            svcModel.clear()
            for (var i = 0; i < list.length; i++) svcModel.append(list[i])
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) { if (viewingSearch) search(); else showRunning() }
        }
    }

    Component.onCompleted: showRunning()

    ListModel { id: svcModel }

    // Only Stop/Disable go through this -- Start/Enable can't strand you
    // (e.g. cut your own SSH/network session), so they stay one-click.
    Controls.Dialog {
        id: confirmSvc
        title: "Confirm"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingUnit: ""
        property bool pendingStart: false
        property bool pendingIsEnable: false
        onAccepted: {
            busy = true
            if (pendingIsEnable) backend.setServiceEnabled(pendingUnit, pendingStart)
            else backend.setServiceActive(pendingUnit, pendingStart)
        }
        Controls.Label {
            text: (confirmSvc.pendingIsEnable ? "Disable " : "Stop ") + confirmSvc.pendingUnit + "?"
                + (confirmSvc.pendingIsEnable ? " It won't start automatically at boot." : " Anything depending on it may stop working.")
            wrapMode: Text.Wrap
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
            Controls.TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Search all services, e.g. sshd, docker"
                enabled: !busy
                onAccepted: search()
            }
            Controls.Button {
                text: "Search"
                enabled: !busy && searchField.text.length > 0
                onClicked: search()
            }
            Controls.Button {
                text: "Show running"
                enabled: !busy
                onClicked: { searchField.text = ""; showRunning() }
            }
        }

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
                Kirigami.Heading {
                    level: 3
                    text: viewingSearch ? "Search results" : "Currently running"
                }
                Repeater {
                    model: svcModel
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: index > 0 ? Kirigami.Units.largeSpacing : 0
                        spacing: Kirigami.Units.smallSpacing
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Label { text: unit; font.bold: true }
                            Controls.Label {
                                text: active
                                color: active === "active" ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                            }
                            Controls.Label { text: "· " + unitEnabled; opacity: 0.7 }
                            Item { Layout.fillWidth: true }
                        }
                        Controls.Label {
                            visible: desc !== undefined && desc.length > 0
                            text: desc
                            opacity: 0.7
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Button {
                                text: active === "active" ? "Stop" : "Start"
                                enabled: !busy
                                onClicked: {
                                    if (active === "active") {
                                        confirmSvc.pendingUnit = unit
                                        confirmSvc.pendingStart = false
                                        confirmSvc.pendingIsEnable = false
                                        confirmSvc.open()
                                    } else {
                                        busy = true
                                        backend.setServiceActive(unit, true)
                                    }
                                }
                            }
                            Controls.Button {
                                text: unitEnabled === "enabled" ? "Disable" : "Enable"
                                enabled: !busy
                                onClicked: {
                                    if (unitEnabled === "enabled") {
                                        confirmSvc.pendingUnit = unit
                                        confirmSvc.pendingStart = false
                                        confirmSvc.pendingIsEnable = true
                                        confirmSvc.open()
                                    } else {
                                        busy = true
                                        backend.setServiceEnabled(unit, true)
                                    }
                                }
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: svcModel.count === 0 && !busy
                    text: viewingSearch ? "No matches." : "No services currently running."
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
