import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Gaming"

    property bool busy: false
    property bool steamInstalled: false
    property bool gamemodeInstalled: false
    property string statusText: ""
    property bool statusOk: true
    property bool showLog: false

    property var emuSystems: []
    property var emuGames: []
    property var emuSelected: ({})
    property var emuSettings: ({ fullscreen: true, picture: "fill", resolution: 1 })
    property var controllers: []
    property var bios: []
    property bool anyEmulatorInstalled: false

    readonly property var pictureModes: ["sharp", "fill", "smooth"]
    readonly property var resolutions: [1, 2, 4]

    function refreshStatus() {
        var status = backend.gamingStatus()
        steamInstalled = status.steamInstalled
        gamemodeInstalled = status.gamemodeInstalled
        emuSystems = backend.emulationSystems()
        emuGames = backend.emulationGames()
        emuSettings = backend.emulationSettings()
        controllers = backend.gameControllers()
        bios = backend.biosReport()
        var any = false
        for (var i = 0; i < emuSystems.length; i++) if (emuSystems[i].installed) any = true
        anyEmulatorInstalled = any
    }

    function selectedSystems() {
        var ids = []
        for (var id in emuSelected) if (emuSelected[id]) ids.push(id)
        return ids
    }

    function startJob() {
        busy = true
        logArea.text = ""
        statusText = "Working..."
        statusOk = true
    }

    function saveSettings(changes) {
        var s = Object.assign({}, emuSettings, changes)
        emuSettings = s
        backend.setEmulationSettings(s)
    }

    Component.onCompleted: refreshStatus()

    Connections {
        target: backend
        function onGamingProgress(line) {
            logArea.append(line)
            if (line.length > 0 && line.charAt(0) !== "$") statusText = line
        }
        function onGamingFinished(ok, message) {
            busy = false
            statusOk = ok
            statusText = message
            logArea.append(ok ? "\n✓ " + message : "\n✗ " + message)
            if (ok) emuSelected = ({})
            refreshStatus()
        }
        function onControllerSetupStep(index, total, title, hint) {
            setupDialog.stepIndex = index
            setupDialog.stepTotal = total
            setupDialog.prompt = title
            setupDialog.hint = hint
        }
        function onControllerSetupDone(ok, message) {
            setupDialog.running = false
            setupDialog.close()
            controllers = backend.gameControllers()
        }
    }

    Controls.Dialog {
        id: setupDialog
        property string padName: ""
        property int stepIndex: 0
        property int stepTotal: 1
        property string prompt: ""
        property string hint: ""
        property bool running: false
        title: "Set up " + padName
        modal: true
        anchors.centerIn: parent
        width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 26)
        closePolicy: Controls.Popup.NoAutoClose
        onRejected: if (running) backend.cancelControllerSetup()
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.largeSpacing
            Controls.Label {
                text: "Step " + (setupDialog.stepIndex + 1) + " of " + setupDialog.stepTotal
                opacity: 0.7
            }
            Kirigami.Heading {
                Layout.fillWidth: true
                level: 2
                wrapMode: Text.Wrap
                text: setupDialog.prompt
            }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                visible: setupDialog.hint.length > 0
                text: setupDialog.hint
            }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                opacity: 0.7
                text: "No such button on your controller? Press Skip."
            }
        }
        footer: Controls.DialogButtonBox {
            Controls.Button {
                text: "Skip"
                icon.name: "go-next-skip"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.ActionRole
                onClicked: backend.skipControllerStep()
            }
            Controls.Button {
                text: "Cancel"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.RejectRole
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
                    onClicked: { startJob(); backend.installGaming() }
                }
            }
        }

        // Install progress: a status line, with the raw log behind "Show details".
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: busy || statusText.length > 0
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                ReyOSProgressBar {
                    Layout.fillWidth: true
                    indeterminate: busy
                    visible: busy
                }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: statusText
                        color: busy ? Kirigami.Theme.textColor
                             : (statusOk ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor)
                    }
                    Controls.Button {
                        text: showLog ? "Hide details" : "Show details"
                        flat: true
                        onClicked: showLog = !showLog
                    }
                }
                Controls.ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Kirigami.Units.gridUnit * 10
                    visible: showLog
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
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Button {
                        text: "Install selected"
                        highlighted: true
                        enabled: !busy && selectedSystems().length > 0
                        onClicked: { startJob(); backend.installEmulation(selectedSystems()) }
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

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Display"; level: 3 }
                Controls.Switch {
                    text: "Play in full screen"
                    checked: emuSettings.fullscreen
                    onToggled: saveSettings({ fullscreen: checked })
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: Kirigami.Units.largeSpacing
                    Controls.Label { text: "Picture" }
                    Controls.ComboBox {
                        Layout.fillWidth: true
                        model: ["Sharp pixels, exact size (may leave borders)", "Sharp pixels, fill the screen", "Smooth, fill the screen"]
                        currentIndex: Math.max(0, pictureModes.indexOf(emuSettings.picture))
                        onActivated: saveSettings({ picture: pictureModes[currentIndex] })
                    }
                    Controls.Label { text: "3D resolution" }
                    Controls.ComboBox {
                        Layout.fillWidth: true
                        model: ["Original (fastest)", "2× (needs a graphics card)", "4× (needs a strong graphics card)"]
                        currentIndex: Math.max(0, resolutions.indexOf(emuSettings.resolution))
                        onActivated: saveSettings({ resolution: resolutions[currentIndex] })
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "3D resolution applies to Nintendo 64, PlayStation, PSP, Nintendo DS and GameCube / Wii. If a game stutters, go back to Original."
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Controllers"; level: 3 }
                Controls.Label {
                    visible: controllers.length === 0
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "No controller found. Plug one in (or pair it in Bluetooth settings), then press Refresh."
                }
                Repeater {
                    model: controllers
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Kirigami.Icon { source: "input-gamepad"; implicitWidth: Kirigami.Units.iconSizes.medium; implicitHeight: implicitWidth }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.Label { text: modelData.name; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                            Controls.Label {
                                text: modelData.configured ? "Set up" : "Not set up yet"
                                color: modelData.configured ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
                            }
                        }
                        Controls.Button {
                            text: modelData.configured ? "Set up again" : "Set up"
                            highlighted: !modelData.configured
                            onClicked: {
                                setupDialog.padName = modelData.name
                                setupDialog.prompt = "Getting ready..."
                                setupDialog.hint = ""
                                setupDialog.stepIndex = 0
                                setupDialog.running = true
                                setupDialog.open()
                                backend.startControllerSetup(modelData.path)
                            }
                        }
                    }
                }
                Controls.Button {
                    text: "Refresh"
                    icon.name: "view-refresh"
                    onClicked: controllers = backend.gameControllers()
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "In a game, Start + Select (or the Home button) opens the emulator menu, where you can save, load or quit. Keyboard works too: arrow keys, Z X A S, Enter = Start, F1 = menu, Esc = quit."
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: bios.length > 0
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "BIOS files"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Some systems need files from the real console. Put them in ~/Games/BIOS — ReyOS checks each one and recognises the right file even under a different name."
                }
                Repeater {
                    model: bios
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing
                        Controls.Label {
                            Layout.fillWidth: true
                            font.bold: true
                            text: (modelData.ok ? "✓ " : "✗ ") + modelData.name
                            color: modelData.ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: 0.8
                            text: modelData.summary
                        }
                        Repeater {
                            model: modelData.files
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: Kirigami.Units.gridUnit
                                Controls.Label {
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    text: {
                                        var f = modelData
                                        if (f.status === "ok") return "✓ " + f.name + " — " + f.note
                                        if (f.status === "rename") return "⚠ " + f.name + " — found as " + f.source
                                        if (f.status === "wrong") return "⚠ " + f.name + " — this isn't the right file (checksum doesn't match)"
                                        return "· " + f.name + " — missing (" + f.note + ")"
                                    }
                                    color: modelData.status === "ok" ? Kirigami.Theme.positiveTextColor
                                         : (modelData.status === "missing" ? Kirigami.Theme.textColor : Kirigami.Theme.neutralTextColor)
                                }
                                Controls.Button {
                                    visible: modelData.status === "rename"
                                    text: "Fix name"
                                    onClicked: { backend.biosFixName(modelData.source, modelData.name); bios = backend.biosReport() }
                                }
                            }
                        }
                    }
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Button {
                        text: "Open BIOS folder"
                        icon.name: "folder-open"
                        onClicked: backend.openGamesFolder("bios")
                    }
                    Controls.Button {
                        text: "Check again"
                        icon.name: "view-refresh"
                        onClicked: bios = backend.biosReport()
                    }
                }
            }
        }
    }
}
