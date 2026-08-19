import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Drivers"

    property bool busy: false
    property var gpuModel: []
    property bool needsNvidiaDriver: false

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshDriverStatus()
    }

    Connections {
        target: backend
        function onDriverStatusReady(info) {
            busy = false
            gpuModel = info.gpus
            needsNvidiaDriver = info.needsNvidiaDriver
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    Controls.Dialog {
        id: confirmInstall
        title: "Install NVIDIA drivers?"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: { busy = true; backend.installNvidiaDrivers() }
        Controls.Label {
            width: 360
            wrapMode: Text.Wrap
            text: "Installs nvidia-dkms and nvidia-utils via pacman. This replaces the open-source nouveau driver with NVIDIA's proprietary one, rebuilt automatically on every kernel update. A reboot is needed afterward for it to take effect."
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
            visible: needsNvidiaDriver
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Icon { source: "dialog-warning"; Layout.preferredWidth: Kirigami.Units.iconSizes.medium; Layout.preferredHeight: Kirigami.Units.iconSizes.medium }
                    Kirigami.Heading { text: "NVIDIA driver not installed"; level: 3 }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "This system is running the open-source nouveau driver (or none at all) on NVIDIA hardware. Games and demanding graphics work will run much better with the proprietary NVIDIA driver."
                }
                Controls.Button {
                    text: "Install NVIDIA drivers"
                    highlighted: true
                    enabled: !busy
                    onClicked: confirmInstall.open()
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Detected graphics hardware"; level: 3 }
                Repeater {
                    model: gpuModel
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: Kirigami.Units.smallSpacing
                        Controls.Label { text: modelData.model; wrapMode: Text.Wrap; Layout.fillWidth: true; font.bold: true }
                        Controls.Label {
                            text: "Driver in use: " + (modelData.driver.length > 0 ? modelData.driver : "none")
                            opacity: 0.7
                        }
                    }
                }
                Controls.Label {
                    visible: gpuModel.length === 0 && !busy
                    text: "No graphics hardware detected."
                    opacity: 0.7
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
