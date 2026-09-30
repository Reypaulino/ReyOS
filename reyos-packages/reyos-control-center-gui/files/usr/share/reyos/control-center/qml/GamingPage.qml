import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Gaming"

    property bool busy: false
    property bool steamInstalled: false
    property bool gamemodeInstalled: false

    property var emuSystems: []
    property var emuGames: []
    property var emuSelected: ({})

    function refreshStatus() {
        var status = backend.gamingStatus()
        steamInstalled = status.steamInstalled
        gamemodeInstalled = status.gamemodeInstalled
        emuSystems = backend.emulationSystems()
        emuGames = backend.emulationGames()
    }

    function selectedSystems() {
        var ids = []
        for (var id in emuSelected) if (emuSelected[id]) ids.push(id)
        return ids
    }

    Component.onCompleted: refreshStatus()

    Connections {
        target: backend
        function onGamingProgress(line) {
            logArea.append(line)
        }
        function onGamingFinished(ok, message) {
            busy = false
            logArea.append(ok ? "\n✓ " + message : "\n✗ " + message)
            if (ok) { emuSelected = ({}); refreshStatus() }
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
                Kirigami.Heading { text: "Steam & GameMode"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Installs Steam (with 32-bit compatibility libraries), GameMode (a temporary performance boost while a game is running), and MangoHud (an in-game performance overlay)."
                }
                Controls.Label {
                    Layout.fillWidth: true
                    color: steamInstalled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                    text: "Steam: " + (steamInstalled ? "Installed" : "Not installed")
                }
                Controls.Label {
                    Layout.fillWidth: true
                    color: gamemodeInstalled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                    text: "GameMode: " + (gamemodeInstalled ? "Installed" : "Not installed")
                }
                Controls.Button {
                    text: (steamInstalled && gamemodeInstalled) ? "Reinstall / repair" : "Install"
                    highlighted: true
                    enabled: !busy
                    onClicked: { busy = true; logArea.text = ""; backend.installGaming() }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Emulation"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Play classic console games with RetroArch. Pick the systems you want and ReyOS installs only those emulators (it will ask for your password). ReyOS doesn't include any games or BIOS files — use your own, for example dumped from cartridges and discs you own."
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Kirigami.Units.gridUnit
                    Repeater {
                        model: emuSystems
                        delegate: Controls.CheckBox {
                            Layout.fillWidth: true
                            text: modelData.name + (modelData.installed ? "  ✓ installed" : "") + (modelData.games > 0 ? "  · " + modelData.games + (modelData.games === 1 ? " game" : " games") : "")
                            checked: modelData.installed || emuSelected[modelData.id] === true
                            enabled: !modelData.installed && !busy
                            onToggled: {
                                var s = Object.assign({}, emuSelected)
                                s[modelData.id] = checked
                                emuSelected = s
                            }
                        }
                    }
                }
                Repeater {
                    model: emuSystems
                    delegate: Controls.Label {
                        visible: modelData.bios.length > 0 && (modelData.installed || emuSelected[modelData.id] === true)
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: Kirigami.Theme.neutralTextColor
                        text: modelData.name + ": " + modelData.bios
                    }
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Button {
                        text: "Install selected"
                        highlighted: true
                        enabled: !busy && selectedSystems().length > 0
                        onClicked: { busy = true; logArea.text = ""; backend.installEmulation(selectedSystems()) }
                    }
                    Controls.Button {
                        text: "Open games folder"
                        icon.name: "folder-open"
                        onClicked: backend.openGamesFolder("")
                    }
                    Controls.Button {
                        text: "Refresh"
                        icon.name: "view-refresh"
                        onClicked: refreshStatus()
                    }
                }

                Kirigami.Heading { text: "Your games"; level: 4 }
                Controls.Label {
                    visible: emuGames.length === 0
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "No games yet. Put them in the folder for their system under ~/Games/ROMs (for example ~/Games/ROMs/snes/), then press Refresh."
                }
                Repeater {
                    model: emuGames
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.Label { text: modelData.title; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                            Controls.Label { text: modelData.system; opacity: 0.7; Layout.fillWidth: true }
                        }
                        Controls.Button {
                            text: modelData.playable ? "Play" : "Emulator not installed"
                            icon.name: modelData.playable ? "media-playback-start" : ""
                            enabled: modelData.playable
                            onClicked: backend.launchGame(modelData.systemId, modelData.path)
                        }
                    }
                }
            }
        }

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: busy
            visible: busy
        }

        Controls.ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 160
            visible: logArea.text.length > 0
            Controls.TextArea {
                id: logArea
                readOnly: true
                wrapMode: TextEdit.Wrap
                font.family: "monospace"
                font.pointSize: 9
            }
        }
    }
}
