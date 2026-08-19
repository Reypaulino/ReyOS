import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "ReyOS Home"

    property real cpuPct: 0
    property int memUsed: 0
    property int memTotal: 0
    property int memPct: 0
    property int swapUsed: 0
    property int swapTotal: 0
    property string swapStatus: "OFF"
    property string governor: "N/A"
    property int swappiness: 0
    property string uptime: "N/A"

    property string osName: "…"
    property string kernel: "…"
    property string arch: "…"
    property string hostname: "…"
    property string cpuModel: "…"
    property string gpuModel: "…"

    Component.onCompleted: backend.refreshAboutInfo()

    Connections {
        target: backend
        function onStatsUpdated(s) {
            cpuPct = s.cpu
            memUsed = s.memUsed
            memTotal = s.memTotal
            memPct = s.memPct
            swapUsed = s.swapUsed
            swapTotal = s.swapTotal
            swapStatus = s.swapStatus
            governor = s.governor
            swappiness = s.swappiness
            uptime = s.uptime
        }
        function onAboutInfoReady(info) {
            osName = info.osName
            kernel = info.kernel
            arch = info.arch
            hostname = info.hostname
            cpuModel = info.cpuModel
            gpuModel = info.gpuModel
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
                Controls.Label { Kirigami.FormData.label: "OS:"; text: osName }
                Controls.Label { Kirigami.FormData.label: "Kernel:"; text: kernel + " (" + arch + ")" }
                Controls.Label { Kirigami.FormData.label: "Hostname:"; text: hostname }
                Controls.Label { Kirigami.FormData.label: "CPU:"; text: cpuModel }
                Controls.Label { Kirigami.FormData.label: "GPU:"; text: gpuModel }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Everyday essentials"; level: 3 }
                Controls.Label { text: "The common tasks are here. Advanced controls stay in the sidebar when you need them."; wrapMode: Text.WordWrap; opacity: 0.75; Layout.fillWidth: true }
                GridLayout {
                    columns: width > 610 ? 4 : 2
                    Layout.fillWidth: true
                    columnSpacing: Kirigami.Units.smallSpacing
                    rowSpacing: Kirigami.Units.smallSpacing
                    Controls.Button { text: "Updates"; icon.name: "system-software-update"; Layout.fillWidth: true; onClicked: backend.openPage("UpdatesPage.qml") }
                    Controls.Button { text: "Backup"; icon.name: "document-save"; Layout.fillWidth: true; onClicked: backend.openPage("BackupPage.qml") }
                    Controls.Button { text: "Appearance"; icon.name: "preferences-desktop-theme"; Layout.fillWidth: true; onClicked: backend.openPage("AppearancePage.qml") }
                    Controls.Button { text: "Network"; icon.name: "network-wired"; Layout.fillWidth: true; onClicked: backend.openPage("NetworkPage.qml") }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: RowLayout {
                Kirigami.Icon { source: "utilities-terminal"; implicitWidth: Kirigami.Units.iconSizes.medium; implicitHeight: implicitWidth }
                ColumnLayout {
                    Layout.fillWidth: true
                    Controls.Label { text: "ReyOS System Tools"; font.bold: true }
                    Controls.Label { text: "Open the terminal toolbox for quick system actions."; opacity: 0.7; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
                Controls.Button { text: "Open"; icon.name: "utilities-terminal"; onClicked: backend.openTerminalToolbox() }
            }
        }


        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing

                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "CPU"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label { text: cpuPct.toFixed(1) + "%" }
                }
                Controls.ProgressBar {
                    Layout.fillWidth: true
                    from: 0; to: 100
                    value: cpuPct
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.gridUnit
                    Kirigami.Heading { text: "Memory"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label { text: memUsed + " / " + memTotal + " MB  (" + memPct + "%)" }
                }
                Controls.ProgressBar {
                    Layout.fillWidth: true
                    from: 0; to: 100
                    value: memPct
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.gridUnit
                    Kirigami.Heading { text: "Swap"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label { text: swapUsed + " / " + swapTotal + " MB  ·  " + swapStatus }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: Kirigami.FormLayout {
                Controls.Label { Kirigami.FormData.label: "CPU governor:"; text: governor }
                Controls.Label { Kirigami.FormData.label: "Swappiness:"; text: swappiness }
                Controls.Label { Kirigami.FormData.label: "Uptime:"; text: uptime }
            }
        }
    }
}
