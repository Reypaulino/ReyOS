import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

// Everyday things first (your games, display, controllers); one-time setup
// (emulators, BIOS files, Steam) at the bottom, each folded to one status
// line. Longer explanations sit behind the ⓘ buttons.
Kirigami.ScrollablePage {
    title: "Gaming"

    property bool busy: false
    property bool steamInstalled: false
    property bool gamemodeInstalled: false
    property string statusText: ""
    property bool statusOk: true
    property bool showLog: false

    property var emuSystems: []
    readonly property int gameCount: emuSystems.reduce(function (n, s) { return n + s.games }, 0)
    readonly property int installedCount: emuSystems.filter(function (s) { return s.installed }).length
    property var emuSelected: ({})
    property var emuSettings: ({ fullscreen: true, picture: "fill", resolution: 1 })
    property var controllers: []
    property string player1: backend.player1()
    readonly property var padTypes: [{ id: "xbox", label: "Xbox" }, { id: "playstation", label: "PlayStation" },
                                     { id: "nintendo", label: "Nintendo" }, { id: "generic", label: "Other" }]
    readonly property string padBrand: controllers.length > 0 ? controllers[0].brand : (backend ? backend.savedControllerBrand() : "generic")
    property var systemLayouts: backend.systemControls(padBrand)
    property int layoutIndex: 0
    property string layoutKey: ""
    property var bios: []
    property var shrinkable: ({ count: 0, size: 0 })
    property bool anyEmulatorInstalled: false
    // Setup sections: open on a fresh install (nothing to play yet), folded
    // to their status line once emulators are installed.
    property bool emuExpanded: false
    property bool steamExpanded: false
    property bool expandedLoaded: false
    property bool biosExpanded: false
    property var biosMissing: bios.filter(function (b) { return !b.ok }).map(function (b) { return b.name })
    property var flatpakSystems: emuSystems.filter(function (s) { return s.flatpak && s.installed })

    readonly property var pictureModes: ["clean", "sharp", "fill", "smooth", "lcd"]
    readonly property var resolutions: [1, 2, 4]

    function refreshStatus() {
        var status = backend.gamingStatus()
        steamInstalled = status.steamInstalled
        gamemodeInstalled = status.gamemodeInstalled
        emuSystems = backend.emulationSystems()
        emuSettings = backend.emulationSettings()
        controllers = backend.gameControllers()
        bios = backend.biosReport()
        shrinkable = backend.shrinkableGames()
        var any = false
        for (var i = 0; i < emuSystems.length; i++) if (emuSystems[i].installed) any = true
        anyEmulatorInstalled = any
        if (!expandedLoaded) {
            emuExpanded = !any
            biosExpanded = biosMissing.length > 0 && emuSettings.bios_expanded === true
            expandedLoaded = true
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

    // Display settings apply when a game starts: say so, naming the game
    // that's open now, since it keeps its old settings until restarted.
    property string displayNote: ""
    function saveDisplay(changes) {
        saveSettings(changes)
        var game = backend.runningGame()
        displayNote = game !== "" ? "Saved. Close " + game + " and start it again to see the change."
                                  : "Saved. It applies the next time you start a game."
    }

    function startSetup(pad) {
        setupDialog.padName = pad.name
        setupDialog.prompt = "Getting ready..."
        setupDialog.hint = ""
        setupDialog.stepKey = ""
        setupDialog.stepIndex = 0
        setupDialog.running = true
        setupDialog.open()
        backend.startControllerSetup(pad.path)
    }

    Component.onCompleted: {
        refreshStatus()
        // ReyOS Games' "Controller…" / "Set up" opens this page for it.
        var start = backend.startWith()
        if (start === "controller-setup" && controllers.length > 0)
            Qt.callLater(startSetup, controllers.find(function (c) { return !c.configured }) || controllers[0])
        else if (start.indexOf("buttons:") === 0) {
            // ReyOS Games' right-click "Controller buttons for …".
            var i = systemLayouts.findIndex(function (l) { return l.id === start.slice(8) })
            if (i >= 0) { layoutIndex = i; layoutKey = ""; Qt.callLater(layoutDialog.open) }
        }
    }

    Connections {
        target: backend
        function onGamingProgress(line) {
            logArea.append(line)
            if (line.length > 0 && line.charAt(0) !== "$") statusText = line
        }
        function onBiosChanged() { bios = backend.biosReport() }
        function onPathBrowsed(target, path) {
            if (target === "gameStorage" && path !== "") saveSettings({ game_storage: path })
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

    // "Buttons per system": what each button does on each console. Rarely
    // needed, so it's a window instead of half a page.
    Controls.Dialog {
        id: layoutDialog
        title: "Button layout"
        modal: true
        parent: Controls.Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 44)
        height: Math.min(parent.height - Kirigami.Units.gridUnit * 2, implicitHeight)
        standardButtons: Controls.Dialog.Close
        contentItem: Controls.ScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                id: layoutCard
                width: layoutDialog.availableWidth
                readonly property var current: systemLayouts[Math.min(layoutIndex, systemLayouts.length - 1)] || ({ rows: [], labels: {}, note: "", pad: "" })
                spacing: Kirigami.Units.largeSpacing
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
                    text: "What each button on your controller does on the " + layoutCard.current.pad + ". Pick another button to swap two; it applies the next time you start a game."
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
                                    Controls.Label {
                                        visible: !modelData.movable
                                        text: modelData.yours
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    Controls.ComboBox {
                                        visible: modelData.movable
                                        wheelEnabled: false
                                        Layout.fillWidth: true
                                        model: layoutCard.current.choices
                                        textRole: "label"
                                        currentIndex: Math.max(0, layoutCard.current.choices.findIndex(function (c) { return c.key === modelData.pad }))
                                        onActivated: {
                                            var id = layoutCard.current.id
                                            backend.setButton(id, modelData.key, layoutCard.current.choices[currentIndex].key)
                                            systemLayouts = backend.systemControls(padBrand)
                                        }
                                    }
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
                Controls.Button {
                    visible: layoutCard.current.custom === true
                    text: "Reset " + layoutCard.current.name + " to the usual layout"
                    icon.name: "edit-undo"
                    onClicked: {
                        backend.resetButtons(layoutCard.current.id)
                        systemLayouts = backend.systemControls(padBrand)
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

        // ---- Your games -------------------------------------------------
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Your games"; level: 3 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: gameCount > 0 ? 1 : 0.7
                        text: !anyEmulatorInstalled
                              ? "Play classic console games, from NES to PlayStation 2. Pick the systems you want under Setup below."
                              : gameCount > 0 ? gameCount + (gameCount === 1 ? " game" : " games")
                                              : "No games yet. Press Add games, or put games in ~/Games/ROMs/<system>/."
                    }
                    Controls.Button {
                        visible: anyEmulatorInstalled
                        text: "Add games…"
                        icon.name: "list-add"
                        onClicked: backend.addGames()
                        Controls.ToolTip.visible: hovered
                        Controls.ToolTip.text: "PlayStation 2, PSP or PlayStation games (.7z, .zip, .rar, .iso or .cue). They're shrunk to save space: the same game in a smaller file."
                    }
                    Controls.Button {
                        visible: anyEmulatorInstalled
                        text: "Open game library"
                        icon.name: "view-list-icons"
                        highlighted: gameCount > 0
                        onClicked: backend.openGameLibrary()
                    }
                }
                RowLayout {
                    visible: anyEmulatorInstalled && shrinkable.count > 0
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: (shrinkable.count === 1 ? "1 game" : shrinkable.count + " games") + " (" + (shrinkable.size / 1073741824).toFixed(1)
                              + " GB) can be shrunk to save space: the same game in a smaller file."
                    }
                    Controls.Button {
                        text: shrinkable.count === 1 ? "Shrink it…" : "Shrink them…"
                        icon.name: "package-x-generic"
                        onClicked: backend.shrinkGames()
                    }
                }
                RowLayout {
                    visible: anyEmulatorInstalled
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        opacity: 0.7
                        text: "Added games are kept in " + (emuSettings.game_storage ? emuSettings.game_storage : "~/Games/ROMs")
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "Pick a bigger drive (another partition or an external disk) to keep games off this one. They still show up in the library."
                    }
                    Controls.Button {
                        text: "Change…"
                        flat: true
                        onClicked: backend.browsePath("gameStorage", true)
                    }
                    Controls.Button {
                        visible: !!emuSettings.game_storage
                        text: "Use ~/Games/ROMs"
                        flat: true
                        onClicked: saveSettings({ game_storage: "" })
                    }
                    Controls.Button {
                        text: "Open folder"
                        flat: true
                        onClicked: backend.openGamesFolder("")
                    }
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

        // ---- Display ----------------------------------------------------
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Display"; level: 3 }
                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    visible: displayNote !== ""
                    type: displayNote.indexOf("Close ") === 7 ? Kirigami.MessageType.Warning : Kirigami.MessageType.Positive
                    text: displayNote
                    showCloseButton: true
                    onVisibleChanged: if (!visible) displayNote = ""
                }
                // Switch labels don't wrap: keep them short, details in ⓘ.
                RowLayout {
                    Controls.Switch {
                        text: "Start games in full screen"
                        checked: emuSettings.fullscreen
                        onToggled: saveDisplay({ fullscreen: checked })
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "Applies every time a game starts. To keep one game in a window, right-click it in the game library and choose \"Always play this game in a window\"."
                    }
                }
                RowLayout {
                    Controls.Switch {
                        text: "Show FPS, CPU and GPU while playing"
                        checked: emuSettings.overlay !== false
                        onToggled: saveDisplay({ overlay: checked })
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "Right Shift + F12 hides it during a game. PlayStation 2 and 3DS show their own numbers instead."
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 3
                    columnSpacing: Kirigami.Units.largeSpacing
                    Controls.Label { text: "Picture" }
                    // No mouse wheel on these: scrolling the page over one
                    // used to change the setting without anyone noticing.
                    Controls.ComboBox {
                        wheelEnabled: false
                        Layout.fillWidth: true
                        model: ["Clean pixels, fill the screen (recommended)", "Sharp pixels, exact size (may leave borders)", "Blocky pixels, fill the screen", "Smooth (blurry), fill the screen", "LCD screen look (Game Boy / GBA)"]
                        currentIndex: Math.max(0, pictureModes.indexOf(emuSettings.picture))
                        onActivated: saveDisplay({ picture: pictureModes[currentIndex] })
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "How NES, SNES, Game Boy, GBA and Genesis games are drawn. Clean and LCD use the shader pack installed with the emulators."
                    }
                    Controls.Label { text: "3D resolution" }
                    Controls.ComboBox {
                        wheelEnabled: false
                        Layout.fillWidth: true
                        model: ["Original (fastest)", "2× (sharper)", "4× (sharpest)"]
                        currentIndex: Math.max(0, resolutions.indexOf(emuSettings.resolution))
                        onActivated: saveDisplay({ resolution: resolutions[currentIndex] })
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "For Nintendo 64, Dreamcast, PlayStation 1 and 2, PSP, Nintendo DS and GameCube / Wii. Without a dedicated graphics card, 4× runs as 2× (except PlayStation 2 and PSP). If a game stutters, pick a lower one."
                    }
                }
                RowLayout {
                    visible: flatpakSystems.some(function(s) { return s.id === "ps2" })
                    Controls.Switch {
                        text: "Use these for PlayStation 2 too"
                        checked: emuSettings.ps2_graphics !== false
                        onToggled: saveDisplay({ ps2_graphics: checked })
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "PlayStation 2 then follows 3D resolution and Picture, replacing PCSX2's own graphics settings every time a game starts. Turn it off to set them in PCSX2 yourself."
                    }
                }
                Flow {
                    visible: flatpakSystems.length > 0
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Repeater {
                        model: flatpakSystems
                        delegate: Controls.Button {
                            text: "Open " + modelData.app + " settings"
                            icon.name: "configure"
                            flat: true
                            onClicked: backend.openEmulatorApp(modelData.id)
                        }
                    }
                }
            }
        }

        // ---- Controllers ------------------------------------------------
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            visible: anyEmulatorInstalled
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Controllers"; level: 3; Layout.fillWidth: true }
                    Controls.Button {
                        icon.name: "view-refresh"
                        flat: true
                        onClicked: controllers = backend.gameControllers()
                        Controls.ToolTip.visible: hovered
                        Controls.ToolTip.text: "Look for controllers again"
                    }
                }
                Controls.Label {
                    visible: controllers.length === 0
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: "No controller found. Plug one in or pair it in Bluetooth settings."
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
                        // Only with two or more pads: which one is player 1.
                        Controls.RadioButton {
                            visible: controllers.length > 1
                            text: "Player 1"
                            checked: player1 === modelData.name || (player1 === "" && index === 0)
                            onToggled: if (checked) { player1 = modelData.name; backend.setPlayer1(modelData.name) }
                        }
                        // The pad in your hands, not a console: picked as "Nintendo"
                        // next to "Super Nintendo" it renamed every button.
                        // Only for pads ReyOS can't recognise (or one already
                        // overridden): a recognised pad's names are right, and the
                        // choice next to console names got picked as "Nintendo"
                        // for SNES, renaming every button.
                        Controls.Label {
                            visible: modelData.detected === "generic" || modelData.brand !== modelData.detected
                            text: "Your controller:"
                            opacity: 0.7
                        }
                        Controls.ComboBox {
                            visible: modelData.detected === "generic" || modelData.brand !== modelData.detected
                            wheelEnabled: false
                            model: padTypes.map(function (t) { return { id: t.id, label: t.label + (t.id === modelData.detected ? " (detected)" : "") } })
                            textRole: "label"
                            currentIndex: Math.max(0, padTypes.findIndex(function (t) { return t.id === modelData.brand }))
                            onActivated: {
                                // Back to "detected" when the pick matches what the vendor id says.
                                backend.setPadType(modelData.name, padTypes[currentIndex].id === modelData.detected ? "" : padTypes[currentIndex].id)
                                controllers = backend.gameControllers()
                            }
                            Controls.ToolTip.visible: hovered
                            Controls.ToolTip.text: "The kind of controller you're holding, for button names and pictures. Leave it on \"(detected)\" unless the names don't match your controller. This doesn't change any console's buttons: use Button layout… for that."
                        }
                        Controls.Button {
                            text: modelData.configured ? "Set up again" : "Set up"
                            highlighted: !modelData.configured
                            onClicked: startSetup(modelData)
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "In a game, Start + Select opens the menu (save, load, quit)."
                    }
                    Kirigami.ContextualHelpButton {
                        toolTipText: "The Home button opens it too. Keyboard: arrow keys, Z X A S, Enter = Start, F1 = menu, Esc = quit." + (flatpakSystems.length > 0 ? " PlayStation 2: a connected controller becomes player 1 when a game starts, unless you changed its buttons in PCSX2. 3DS: set its buttons in Azahar's settings." : "")
                    }
                    Controls.Button {
                        visible: systemLayouts.length > 0
                        text: "Button layout…"
                        flat: true
                        onClicked: layoutDialog.open()
                    }
                }
            }
        }

        // ---- Setup ------------------------------------------------------
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Setup"; level: 3 }

                // Emulators
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Controls.Label { text: "Emulators"; font.bold: true }
                        Controls.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            opacity: 0.7
                            text: installedCount > 0 ? installedCount + (installedCount === 1 ? " system installed" : " systems installed")
                                                     : "None yet: pick the systems you want to play"
                        }
                    }
                    Controls.Button {
                        text: emuExpanded ? "Hide" : "Show"
                        icon.name: emuExpanded ? "arrow-up" : "arrow-down"
                        flat: true
                        onClicked: emuExpanded = !emuExpanded
                    }
                }
                ColumnLayout {
                    visible: emuExpanded
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.largeSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            text: "ReyOS installs only the systems you pick. Games and BIOS files aren't included: use your own."
                        }
                        Kirigami.ContextualHelpButton {
                            toolTipText: "RetroArch and its emulators come from the ReyOS/Arch repos (asks for your password). PlayStation 2 and 3DS come from Flathub (no password). Use games and BIOS files dumped from cartridges and discs you own."
                        }
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
                            text: "Refresh"
                            icon.name: "view-refresh"
                            flat: true
                            onClicked: refreshStatus()
                        }
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true; visible: bios.length > 0 }

                // BIOS files
                RowLayout {
                    visible: bios.length > 0
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Controls.Label { text: "BIOS files"; font.bold: true }
                        Controls.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            color: biosMissing.length > 0 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.positiveTextColor
                            text: biosMissing.length > 0 ? "Missing for: " + biosMissing.join(", ")
                                                         : "✓ Everything your emulators need is in place"
                        }
                    }
                    Controls.Button {
                        text: biosExpanded ? "Hide" : "Show"
                        icon.name: biosExpanded ? "arrow-up" : "arrow-down"
                        flat: true
                        onClicked: { biosExpanded = !biosExpanded; backend.setBiosExpanded(biosExpanded) }
                    }
                }
                ColumnLayout {
                    visible: biosExpanded && bios.length > 0
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "Some systems need files from the real console. Press Import BIOS… and pick your own dumped files; ReyOS puts each one where its emulator looks. Keep a backup: ReyOS can't download them for you."
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
                            text: "Import BIOS…"
                            icon.name: "document-import"
                            onClicked: backend.importBios()
                        }
                        Controls.Button {
                            text: "Open BIOS folder"
                            icon.name: "folder-open"
                            flat: true
                            onClicked: backend.openGamesFolder("bios")
                        }
                        Controls.Button {
                            text: "Check again"
                            icon.name: "view-refresh"
                            flat: true
                            onClicked: bios = backend.biosReport()
                        }
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true }

                // Steam & GameMode
                RowLayout {
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Controls.Label { text: "Steam & GameMode"; font.bold: true }
                        Controls.Label {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            opacity: 0.7
                            text: "Steam: " + (steamInstalled ? "installed" : "not installed") + " · GameMode: " + (gamemodeInstalled ? "installed" : "not installed")
                        }
                    }
                    Controls.Button {
                        text: steamExpanded ? "Hide" : "Show"
                        icon.name: steamExpanded ? "arrow-up" : "arrow-down"
                        flat: true
                        onClicked: steamExpanded = !steamExpanded
                    }
                }
                ColumnLayout {
                    visible: steamExpanded
                    Layout.fillWidth: true
                    Layout.leftMargin: Kirigami.Units.largeSpacing
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "Installs Steam, GameMode (a performance boost while a game runs) and the FPS/CPU/GPU overlay."
                    }
                    RowLayout {
                        spacing: Kirigami.Units.largeSpacing
                        Controls.Button {
                            text: (steamInstalled && gamemodeInstalled) ? "Reinstall / repair" : "Install"
                            highlighted: !(steamInstalled && gamemodeInstalled)
                            enabled: !busy
                            onClicked: { startJob(); backend.installGaming() }
                        }
                        Controls.Button {
                            visible: steamInstalled && gamemodeInstalled
                            text: "Use GameMode in all Steam games"
                            icon.name: "games-config-options"
                            enabled: !busy
                            onClicked: { startJob(); backend.applySteamLaunchOptions() }
                        }
                        Kirigami.ContextualHelpButton {
                            visible: steamInstalled && gamemodeInstalled
                            toolTipText: "Steam starts its own games, so GameMode and the overlay go into each game's launch options. Close Steam, then press the button; press it again after installing new games. The overlay follows the switch under Display."
                        }
                    }
                }
            }
        }
    }
}
