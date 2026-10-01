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
    readonly property string padBrand: controllers.length > 0 ? controllers[0].brand : backend.savedControllerBrand()
    property var systemLayouts: backend.systemControls(padBrand)
    property int layoutIndex: 0
    property string layoutKey: ""
    property var bios: []
    property bool anyEmulatorInstalled: false
    property bool emuExpanded: false
    property bool emuExpandedLoaded: false
    property bool biosExpanded: false
    property var biosMissing: bios.filter(function (b) { return !b.ok }).map(function (b) { return b.name })
    property var flatpakSystems: emuSystems.filter(function (s) { return s.flatpak && s.installed })

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
        if (!emuExpandedLoaded) {
            // Collapsed until the user opens it, unless emulators are already
            // installed; after that the user's own choice is remembered.
            emuExpanded = (emuSettings.expanded === true || emuSettings.expanded === false) ? emuSettings.expanded : any
            emuExpandedLoaded = true
            biosExpanded = emuSettings.bios_expanded === true
        }
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
        function onControllerSetupStep(index, total, key, brand, title, hint) {
            setupDialog.stepIndex = index
            setupDialog.stepTotal = total
            setupDialog.stepKey = key
            setupDialog.brand = brand
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
        property string stepKey: ""
        property string brand: "generic"
        property bool running: false
        title: "Set up " + padName
        modal: true
        // Centred in the window, not in the (scrolled) page.
        parent: Controls.Overlay.overlay
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
            ControllerDiagram {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: Math.min(setupDialog.availableWidth, Kirigami.Units.gridUnit * 18)
                Layout.preferredHeight: Layout.preferredWidth * 200 / 320
                activeKey: setupDialog.stepKey
                brand: setupDialog.brand
            }
            Kirigami.Heading {
                // A fixed width (not fillWidth) so wrapped text reports its real
                // height and the dialog grows to fit instead of spilling under the buttons.
                Layout.preferredWidth: setupDialog.availableWidth
                level: 2
                wrapMode: Text.Wrap
                text: setupDialog.prompt
            }
            Controls.Label {
                Layout.preferredWidth: setupDialog.availableWidth
                wrapMode: Text.Wrap
                visible: setupDialog.hint.length > 0
                text: setupDialog.hint
            }
            Controls.Label {
                Layout.preferredWidth: setupDialog.availableWidth
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
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Emulation"; level: 3; Layout.fillWidth: true }
                    Controls.Button {
                        text: emuExpanded ? "Hide" : "Show"
                        icon.name: emuExpanded ? "arrow-up" : "arrow-down"
                        flat: true
                        onClicked: { emuExpanded = !emuExpanded; backend.setEmulationExpanded(emuExpanded) }
                    }
                }
                Controls.Label {
                    visible: !emuExpanded
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: anyEmulatorInstalled ? "Your emulators and games are here — press Show."
                                               : "Play classic console games, from NES to PlayStation 2 and 3DS. Nothing is installed until you choose it — press Show to pick systems."
                }
                ColumnLayout {
                    visible: emuExpanded
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "Play classic console games. Pick the systems you want and ReyOS installs only those emulators — RetroArch from the ReyOS/Arch repos (asks for your password), PlayStation 2 and 3DS from Flathub (no password). ReyOS doesn't include any games or BIOS files — use your own, for example dumped from cartridges and discs you own."
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
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: emuGames.length > 0 ? 1 : 0.7
                            text: emuGames.length > 0
                                  ? emuGames.length + (emuGames.length === 1 ? " game" : " games") + " in ~/Games/ROMs."
                                  : "No games yet. Put them in the folder for their system under ~/Games/ROMs (for example ~/Games/ROMs/n64/), then press Refresh."
                        }
                        Controls.Button {
                            text: "Open game library"
                            icon.name: "view-list-icons"
                            highlighted: emuGames.length > 0
                            onClicked: backend.openGameLibrary()
                        }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled && emuExpanded
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Display"; level: 3 }
                Controls.Switch {
                    text: "Start games in full screen (set it here; RetroArch applies this at every launch)"
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
                    text: "3D resolution applies to Nintendo 64, Dreamcast, PlayStation, PSP, Nintendo DS and GameCube / Wii. It does not change NES, SNES, Game Boy, GBA or Genesis games, which are drawn at their original size (use Picture for those). If a game stutters, go back to Original."
                }
                Controls.Label {
                    visible: flatpakSystems.length > 0
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "PlayStation 2 and 3DS use their own emulator apps: full screen follows the switch above, everything else (resolution, controller buttons) is in the app's own settings."
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Repeater {
                        model: flatpakSystems
                        delegate: Controls.Button {
                            text: "Open " + modelData.app + " settings"
                            icon.name: "configure"
                            onClicked: backend.openEmulatorApp(modelData.id)
                        }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled && emuExpanded
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
                                setupDialog.stepKey = ""
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
                    text: "In a game, Start + Select (or the Home button) opens the emulator menu, where you can save, load or quit. Keyboard works too: arrow keys, Z X A S, Enter = Start, F1 = menu, Esc = quit." + (flatpakSystems.length > 0 ? " PlayStation 2 and 3DS recognise common controllers on their own; change their buttons in the app's settings." : "")
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled && emuExpanded && systemLayouts.length > 0
            contentItem: ColumnLayout {
                id: layoutCard
                readonly property var current: systemLayouts[Math.min(layoutIndex, systemLayouts.length - 1)] || ({ rows: [], labels: {}, note: "", pad: "" })
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Buttons per system"; level: 3 }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Label { text: "System:" }
                    Controls.ComboBox {
                        Layout.fillWidth: true
                        Layout.maximumWidth: Kirigami.Units.gridUnit * 18
                        model: systemLayouts
                        textRole: "name"
                        currentIndex: layoutIndex
                        onActivated: index => { layoutIndex = index; layoutKey = "" }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    visible: layoutCard.current.rows.length > 0
                    text: "What each button on your controller does on the " + layoutCard.current.pad + ". Pick a row to see where the button is."
                }
                GridLayout {
                    Layout.fillWidth: true
                    visible: layoutCard.current.rows.length > 0
                    columns: layoutCard.width > Kirigami.Units.gridUnit * 34 ? 2 : 1
                    columnSpacing: Kirigami.Units.gridUnit
                    rowSpacing: Kirigami.Units.largeSpacing
                    ControllerDiagram {
                        Layout.alignment: Qt.AlignTop | Qt.AlignHCenter
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
                        Layout.preferredHeight: Layout.preferredWidth * 200 / 320
                        brand: padBrand
                        overrides: layoutCard.current.labels
                        activeKey: layoutKey
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: 0
                        Repeater {
                            model: layoutCard.current.rows
                            delegate: Controls.ItemDelegate {
                                Layout.fillWidth: true
                                highlighted: layoutKey === modelData.key
                                onClicked: layoutKey = (layoutKey === modelData.key ? "" : modelData.key)
                                contentItem: RowLayout {
                                    Controls.Label {
                                        text: modelData.console
                                        font.bold: true
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 9
                                        elide: Text.ElideRight
                                    }
                                    Controls.Label { text: "→"; opacity: 0.6 }
                                    Controls.Label { text: modelData.yours; Layout.fillWidth: true; elide: Text.ElideRight }
                                }
                            }
                        }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    visible: layoutCard.current.note.length > 0
                    text: layoutCard.current.note
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: bios.length > 0 && emuExpanded
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "BIOS files"; level: 3; Layout.fillWidth: true }
                    Controls.Button {
                        text: biosExpanded ? "Hide" : "Show"
                        icon.name: biosExpanded ? "arrow-up" : "arrow-down"
                        flat: true
                        onClicked: { biosExpanded = !biosExpanded; backend.setBiosExpanded(biosExpanded) }
                    }
                }
                Controls.Label {
                    visible: !biosExpanded
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: biosMissing.length > 0 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.positiveTextColor
                    text: biosMissing.length > 0 ? "Missing for: " + biosMissing.join(", ") + " — press Show."
                                                 : "✓ Everything your emulators need is in place."
                }
                ColumnLayout {
                    visible: biosExpanded
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
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
}
