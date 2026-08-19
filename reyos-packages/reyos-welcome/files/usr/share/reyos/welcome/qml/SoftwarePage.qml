import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    title: ""
    padding: 0

    property bool allowPanelEditing: false
    property var groups: [
        {
            label: "Gaming",
            apps: [
                { id: "steam", label: "Steam", desc: "Game store & launcher", checked: false },
                { id: "lutris", label: "Lutris", desc: "Manage non-Steam & Windows games", checked: false },
                { id: "retroarch", label: "RetroArch", desc: "Retro console emulation", checked: false },
                { id: "perf-tools", label: "Performance Tools", desc: "GameMode, MangoHud", checked: false },
            ]
        },
        {
            label: "Windows Compatibility",
            apps: [
                { id: "wine", label: "Wine", desc: "Run Windows apps & games", checked: false },
            ]
        },
        {
            label: "Dev Tools",
            apps: [
                { id: "git", label: "Git", desc: "Version control", checked: false },
                { id: "docker", label: "Docker", desc: "Containers", checked: false },
                { id: "neovim", label: "Neovim", desc: "Terminal text editor", checked: false },
                { id: "base-devel", label: "Base Dev Tools", desc: "Compilers & build tools", checked: false },
                { id: "vscode", label: "VS Code", desc: "Code editor", checked: false },
            ]
        },
        {
            label: "Browsers",
            apps: [
                { id: "brave", label: "Brave", desc: "Privacy-focused browser", checked: false },
                { id: "opera", label: "Opera", desc: "Feature-rich browser", checked: false },
                { id: "chromium", label: "Chromium", desc: "Open-source Chrome base", checked: false },
            ]
        },
        {
            label: "Creative",
            apps: [
                { id: "gimp", label: "GIMP", desc: "Image editor", checked: false },
                { id: "krita", label: "Krita", desc: "Digital painting", checked: false },
                { id: "obs-studio", label: "OBS Studio", desc: "Screen recording & streaming", checked: false },
            ]
        },
        {
            label: "Office",
            apps: [
                { id: "libreoffice", label: "LibreOffice", desc: "Office suite", checked: false },
            ]
        },
        {
            label: "System",
            apps: [
                { id: "timeshift", label: "Timeshift", desc: "System restore — create & roll back to snapshots", checked: false },
                { id: "btop", label: "btop", desc: "System monitor — CPU, GPU, RAM, disk, network", checked: false },
                { id: "partitionmanager", label: "KDE Partition Manager", desc: "Disk & partition management", checked: false },
                { id: "fwupd", label: "Firmware Updater", desc: "BIOS/SSD/peripheral firmware updates", checked: false },
                { id: "filelight", label: "Filelight", desc: "Visualize disk space usage", checked: false },
                { id: "bleachbit", label: "BleachBit", desc: "Clean cache, temp files & free up space", checked: false },
            ]
        },
    ]

    background: Rectangle { color: ReyOSStyle.bg }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing * 2
        spacing: Kirigami.Units.largeSpacing

        Controls.Label {
            text: "Pick what you'd like installed"
            font.pointSize: 20
            font.bold: true
            color: ReyOSStyle.text
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 0

            Controls.CheckBox {
                checked: allowPanelEditing
                onToggled: allowPanelEditing = checked
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Leave this off to keep the recommended ReyOS panel layout protected. Turn it on to unlock panel editing after setup."
            }
            Controls.Label {
                text: "Customize ReyOS panels"
                color: ReyOSStyle.text
            }
        }

        Controls.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                width: parent.width
                spacing: Kirigami.Units.largeSpacing

                Repeater {
                    model: groups
                    delegate: ColumnLayout {
                        id: groupDelegate
                        required property var modelData
                        required property int index
                        readonly property int groupIndex: index
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Controls.Label {
                            text: groupDelegate.modelData.label
                            font.bold: true
                            font.pointSize: 13
                            color: ReyOSStyle.accent
                            Layout.topMargin: groupDelegate.groupIndex > 0 ? Kirigami.Units.largeSpacing : 0
                        }

                        Repeater {
                            model: groupDelegate.modelData.apps
                            delegate: RowLayout {
                                required property var modelData
                                required property int index
                                Layout.fillWidth: true
                                Layout.leftMargin: Kirigami.Units.largeSpacing
                                Controls.CheckBox {
                                    checked: modelData.checked
                                    onCheckedChanged: groups[groupDelegate.groupIndex].apps[index].checked = checked
                                }
                                ColumnLayout {
                                    spacing: 0
                                    Controls.Label { text: modelData.label; color: ReyOSStyle.text }
                                    Controls.Label { text: modelData.desc; color: ReyOSStyle.text; opacity: 0.7; font.pointSize: 9 }
                                }
                            }
                        }
                    }
                }
            }
        }

        Controls.Button {
            text: "Looking for something else? Open the Software Center"
            flat: true
            onClicked: backend.openDiscover()
        }

        RowLayout {
            Layout.fillWidth: true
            Controls.Button {
                text: "Back"
                onClicked: applicationWindow().pageStack.pop()
            }
            Item { Layout.fillWidth: true }
            Controls.Button {
                text: "Next"
                highlighted: true
                onClicked: {
                    backend.setPanelEditing(allowPanelEditing)
                    const selected = []
                    for (const g of groups) {
                        for (const a of g.apps) {
                            if (a.checked) selected.push({ id: a.id, label: a.label })
                        }
                    }
                    applicationWindow().pageStack.push(Qt.resolvedUrl("SummaryPage.qml"), { selectedApps: selected })
                }
            }
        }
    }
}
