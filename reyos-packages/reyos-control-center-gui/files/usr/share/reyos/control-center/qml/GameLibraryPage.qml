import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.Page {
    id: libraryPage
    title: "Game Library"
    padding: Kirigami.Units.largeSpacing

    property var allGames: []
    property var systems: []
    property string gameFilter: ""
    property string gameSearch: ""
    property bool boxart: true
    // "Add games": progress text/percent while busy (percent < 0 = no
    // estimate), then the result and the downloads that may be deleted.
    property bool adding: false
    property string addText: ""
    property real addPercent: -1
    property var addOriginals: []
    property var controllers: []
    readonly property var unconfiguredPad: controllers.find(function (c) { return !c.configured }) || null
    property var setupPad: ({})
    // "Play on another device": only when Remote Play is installed and its
    // switch (Control Center → Gaming → Remote Play) is on.
    property bool showRemotePlay: remotePlay.showInGames()

    // The step-by-step setup runs right here (same steps as Control Center).
    function setUpController(pad) {
        controllers = backend.controllers()
        var p = pad || backend.player1Controller()
        if (!p || !p.path) {
            applicationWindow().notify("No controller found. Plug one in, or pair it in Control Center > Bluetooth.", false)
            return
        }
        // One window at a time: the button window would cover the setup.
        reopenButtons = buttonsDialog.visible
        // The system you're looking at: the button window's, else the chosen console's.
        var system = reopenButtons ? buttonsDialog.layout : (consoleFilter !== "" ? backend.buttonLayout(consoleFilter) : null)
        buttonsDialog.close()
        setupDialog.start(p, system)
    }
    property bool reopenButtons: false

    ControllerSetupDialog {
        id: setupDialog
        onFinished: function (ok, message) {
            controllers = backend.controllers()
            if (reopenButtons) { reopenButtons = false; buttonsDialog.changed(); buttonsDialog.open() }
            if (message) applicationWindow().notify(message, ok)
        }
    }

    // Tabs: All, Windows games, Emulators; on Emulators a dropdown picks one
    // console. gameFilter: "" (all), "pc", "emu" (every console) or a
    // console's id. The "(needs a fast PC)" hint stays on the Gaming page.
    property var consoleSystems: {
        var list = []
        for (var i = 0; i < systems.length; i++)
            if (systems[i].id !== "pc" && systems[i].games > 0)
                list.push({ id: systems[i].id, games: systems[i].games,
                            label: systems[i].name.replace(/ \(needs a fast PC\)/, "") + "  " + systems[i].games })
        return list
    }
    readonly property int consoleTotal: consoleSystems.reduce(function (n, s) { return n + s.games }, 0)
    readonly property int pcTotal: allGames.length - consoleTotal
    // Always all three, so Windows games can be found before the first one
    // is added (an empty tab explains how).
    property var gameTabs: [{ id: "", label: "All  " + allGames.length },
                            { id: "pc", label: "Windows games  " + pcTotal },
                            { id: "emu", label: "Emulators  " + consoleTotal }]
    readonly property string tabFilter: gameFilter === "" || gameFilter === "pc" ? gameFilter : "emu"
    // The one console shown, if any ("" on All / Windows games / every console).
    readonly property string consoleFilter: tabFilter === "emu" && gameFilter !== "emu" ? gameFilter : ""
    property bool filterChosen: false

    function filterValid(f) {
        return f === "" || f === "pc" || f === "emu"
               || consoleSystems.some(function (s) { return s.id === f })
    }

    function startAdding(text) {
        adding = true
        addText = text
        addPercent = -1
        addOriginals = []
        addResult.visible = false
    }

    function addGames() {
        if (adding) return
        startAdding("Choose games to add...")
        backend.addGames()
    }

    readonly property var resolutionNames: ({ 1: "Original", 2: "2×", 3: "3×", 4: "4×" })
    property int defaultResolution: 1

    // A game's own 3D resolution (0 = Control Center's). Applies the next
    // time the game starts.
    function setResolution(index, path, value) {
        backend.setGameResolution(path, value)
        gameModel.setProperty(index, "resolution", value)
        for (var i = 0; i < allGames.length; i++)
            if (allGames[i].path === path) allGames[i].resolution = value
        applicationWindow().notify(value === 0 ? "This game follows Control Center's 3D resolution again."
                                   : "3D resolution for this game: " + resolutionNames[value] + ". Close the game and start it again to see it.")
    }

    function addPcGame() {
        if (adding) return
        startAdding("Getting ready to add a PC game...")
        backend.addPcGame()
    }

    // A PC game's own graphics card ("" = Control Center's choice), like
    // the 3D resolution above. Applies the next time the game starts.
    property string defaultGpu: "nvidia"
    readonly property var gpuNames: ({ nvidia: "NVIDIA", builtin: "built-in" })
    function setGpu(index, path, value) {
        backend.setGameGpu(path, value)
        gameModel.setProperty(index, "gpu", value)
        for (var i = 0; i < allGames.length; i++)
            if (allGames[i].path === path) allGames[i].gpu = value
        applicationWindow().notify(value === "" ? "This game follows Control Center's graphics card again."
                                   : "Graphics card for this game: " + gpuNames[value] + ". It applies the next time it starts.")
    }

    function shrinkGame(path, title) {
        if (adding) return
        startAdding("Shrinking " + title + "...")
        backend.shrinkGame(path)
    }

    actions: [
        Kirigami.Action {
            text: "Add games…"
            icon.name: "list-add"
            enabled: !adding
            tooltip: "Add PlayStation 2, PSP or PlayStation games (.7z, .zip, .rar, .iso or .cue). They're shrunk to save space: the same game in a smaller file."
            onTriggered: addGames()
        },
        Kirigami.Action {
            text: "Add PC game…"
            icon.name: "applications-games"
            enabled: !adding
            tooltip: "Add a Windows game: its installer (setup.exe) or the .exe of a game that's already installed. It runs through Lutris and Proton, with GameMode, the overlay and (on a laptop) the NVIDIA card set up for you."
            onTriggered: addPcGame()
        },
        Kirigami.Action {
            text: "Controller…"
            icon.name: "input-gamepad"
            tooltip: "Set up your controller for games: press each button it shows."
            onTriggered: setUpController(null)
        },
        Kirigami.Action {
            text: "Play on another device…"
            icon.name: "video-display"
            visible: showRemotePlay
            tooltip: "Stream your games to a TV, phone or tablet with Moonlight (Remote Play)."
            onTriggered: { remotePlayDialog.open(); remotePlayPanel.refresh() }
        },
        Kirigami.Action {
            text: "Set up emulators"
            icon.name: "configure"
            onTriggered: backend.openSetup()
        },
        Kirigami.Action {
            text: "Open games folder"
            icon.name: "folder-open"
            onTriggered: backend.openGamesFolder(gameFilter === "emu" ? "" : gameFilter)
        },
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: { gamesSignature = ""; reload() }
        }
    ]

    property string gamesSignature: ""

    function reload() {
        showRemotePlay = remotePlay.showInGames()
        var games = backend.emulationGames()
        // Only rebuild the grid when something changed, so a focus-change
        // rescan doesn't lose the scroll position.
        var sig = JSON.stringify(games.map(function (g) { return [g.path, g.playable, g.cover] }))
        systems = backend.emulationSystems()
        controllers = backend.controllers()
        defaultResolution = backend.defaultResolution()
        defaultGpu = backend.defaultGpu()
        boxart = backend.boxartEnabled()
        if (sig !== gamesSignature) {
            gamesSignature = sig
            allGames = games
            // "All" unless a tab was picked (and still has games).
            if (!filterChosen || !filterValid(gameFilter))
                gameFilter = ""
            applyFilter()
            syncTab()
        }
        backend.fetchCovers()
    }

    function applyFilter() {
        gameModel.clear()
        var q = gameSearch.toLowerCase()
        for (var i = 0; i < allGames.length; i++) {
            var g = allGames[i]
            // A search looks through every system, not just the open tab.
            if ((q !== "" ? g.title.toLowerCase().indexOf(q) >= 0
                          : (gameFilter === "" || g.systemId === gameFilter
                             || (gameFilter === "emu" && g.systemId !== "pc"))))
                gameModel.append(g)
        }
    }

    // Set, not bound: clicking a tab breaks a currentIndex binding, after
    // which the highlighted tab and the listed games could disagree.
    // From gameFilter itself: inside onGameFilterChanged the tabFilter and
    // consoleFilter bindings can still hold the old value (seen in testing:
    // the old tab stayed highlighted, the dropdown kept "All consoles").
    function syncTab() {
        var tab = gameFilter === "" || gameFilter === "pc" ? gameFilter : "emu"
        systemTabs.currentIndex = Math.max(0, gameTabs.findIndex(function (t) { return t.id === tab }))
        var console = tab === "emu" && gameFilter !== "emu" ? gameFilter : ""
        consolePicker.currentIndex = Math.max(0, consoleSystems.findIndex(function (s) { return s.id === console }) + 1)
    }

    onGameFilterChanged: { applyFilter(); syncTab() }
    onGameSearchChanged: applyFilter()
    Component.onCompleted: {
        reload()
        var start = backend.startWith()
        if (start === "add") addGames()
        else if (start === "shrink" && !adding) {
            startAdding("Shrinking your games...")
            backend.shrinkAll()
        }
        else if (start.indexOf("buttons:") === 0) buttonsDialog.openFor(start.slice(8))
    }

    // Also rescan when the window comes back to the front (a game added
    // while it was open in the background, or an emulator just installed).
    Connections {
        target: libraryPage.Window.window
        function onActiveChanged() { if (libraryPage.Window.window.active) reload() }
    }

    ListModel { id: gameModel }

    // A system's buttons: which button on your controller does each
    // console button, changed here (a swap, so nothing is doubled). Same
    // settings as Control Center > Gaming > Button layout.
    Kirigami.Dialog {
        id: buttonsDialog
        property string systemId: ""
        property var layout: ({})
        function openFor(id) {
            systemId = id
            changed()
            open()
        }
        function changed() {
            layout = backend.buttonLayout(systemId)
            pad = backend.player1Controller()
        }
        property var pad: ({})
        title: "Controller: " + (layout.name || "").replace(" (needs a fast PC)", "")
        preferredWidth: Kirigami.Units.gridUnit * 24
        maximumWidth: Kirigami.Units.gridUnit * 24
        padding: Kirigami.Units.largeSpacing * 2
        standardButtons: Kirigami.Dialog.Close
        customFooterActions: [
            Kirigami.Action {
                text: "Reset"
                icon.name: "edit-undo"
                visible: buttonsDialog.layout.custom === true
                onTriggered: {
                    backend.resetButtons(buttonsDialog.systemId)
                    buttonsDialog.changed()
                    applicationWindow().notify((buttonsDialog.layout.name || "") + " buttons are back to the usual layout.")
                }
            }
        ]

        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing

            // Your controller first: set it up here before changing buttons.
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: "input-gamepad"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Controls.Label {
                        Layout.fillWidth: true
                        text: buttonsDialog.pad.name || "No controller found"
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: !buttonsDialog.pad.name ? "Plug one in, or pair it in Control Center > Bluetooth."
                              : buttonsDialog.pad.configured ? "Set up for games." : "Not set up yet: press Set up and follow the steps."
                        color: buttonsDialog.pad.name && !buttonsDialog.pad.configured ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
                    }
                }
                Controls.Button {
                    text: buttonsDialog.pad.configured ? "Set up again" : "Set up"
                    icon.name: "input-gamepad"
                    highlighted: !!buttonsDialog.pad.name && !buttonsDialog.pad.configured
                    enabled: !!buttonsDialog.pad.path
                    onClicked: setUpController(buttonsDialog.pad)
                }
            }

            Kirigami.Separator { Layout.fillWidth: true }

            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                opacity: 0.75
                text: (buttonsDialog.layout.rows || []).length === 0 ? "This system has no button layout to change."
                      : "Left: the " + (buttonsDialog.layout.name || "console").replace(" (needs a fast PC)", "") + " button. Right: the button you press for it. Picking one that's taken swaps the two."
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: Kirigami.Units.largeSpacing * 2
                rowSpacing: Kirigami.Units.smallSpacing

                Repeater {
                    model: buttonsDialog.layout.rows || []
                    delegate: Controls.Label {
                        Layout.row: index
                        Layout.column: 0
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                        text: modelData.console
                        font.bold: true
                        elide: Text.ElideRight
                    }
                }
                Repeater {
                    model: buttonsDialog.layout.rows || []
                    delegate: Item {
                        Layout.row: index
                        Layout.column: 1
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 12
                        implicitHeight: combo.implicitHeight
                        Controls.Label {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !modelData.movable
                            text: modelData.yours
                            opacity: 0.7
                        }
                        Controls.ComboBox {
                            id: combo
                            visible: modelData.movable
                            anchors.left: parent.left
                            anchors.right: parent.right
                            wheelEnabled: false
                            model: buttonsDialog.layout.choices || []
                            textRole: "label"
                            currentIndex: Math.max(0, (buttonsDialog.layout.choices || []).findIndex(function (c) { return c.key === modelData.pad }))
                            onActivated: {
                                var choice = buttonsDialog.layout.choices[currentIndex]
                                backend.setButton(buttonsDialog.systemId, modelData.key, choice.key)
                                buttonsDialog.changed()
                                applicationWindow().notify((buttonsDialog.layout.name || "") + " " + modelData.console + " is now " + choice.label
                                                           + " on your controller. Close the game and start it again to use it.")
                            }
                        }
                    }
                }
            }

            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                visible: !!buttonsDialog.layout.note
                text: buttonsDialog.layout.note || ""
                opacity: 0.75
            }
        }
    }

    Kirigami.Dialog {
        id: remotePlayDialog
        title: "Play on another device"
        preferredWidth: Kirigami.Units.gridUnit * 34
        padding: Kirigami.Units.largeSpacing
        standardButtons: Kirigami.Dialog.Close
        customFooterActions: [
            Kirigami.Action {
                text: "Don't show this here"
                icon.name: "view-hidden"
                tooltip: "Hides this button. Turn it back on in Control Center → Gaming → Remote Play."
                onTriggered: {
                    remotePlay.setShowInGames(false)
                    showRemotePlay = false
                    remotePlayDialog.close()
                }
            },
            Kirigami.Action {
                text: "More settings"
                icon.name: "configure"
                onTriggered: backend.openRemotePlaySetup()
            }
        ]
        // A fixed width: the panel's help text would otherwise ask for a
        // window as wide as its longest paragraph.
        Item {
            implicitWidth: Kirigami.Units.gridUnit * 32
            implicitHeight: remotePlayPanel.implicitHeight
            RemotePlayPanel {
                id: remotePlayPanel
                width: parent.width
                allowInstall: false
                showGamesSwitch: false
            }
        }
    }

    // Adding a PC game ends with this window, not just a line at the top.
    Kirigami.PromptDialog {
        id: pcAddDialog
        property bool ok: true
        property string path: ""
        title: ok ? "Game added" : "Couldn't add the game"
        standardButtons: Kirigami.Dialog.Ok
        customFooterActions: [
            Kirigami.Action {
                text: "Play now"
                icon.name: "media-playback-start"
                visible: pcAddDialog.ok && pcAddDialog.path !== ""
                onTriggered: {
                    pcAddDialog.close()
                    backend.launchGame("pc", pcAddDialog.path)
                }
            }
        ]
    }

    // Right-click > Scan for viruses (Windows games): result window.
    property bool gameScanning: false
    Kirigami.PromptDialog {
        id: scanDialog
        property var report: ({ findings: [] })
        title: report.status === "found" ? "Threat found"
               : report.status === "clean" ? "No known threats found"
               : report.status === "no_scanner" ? "Malware scanner not set up"
               : "Not verified"
        subtitle: report.status === "no_scanner"
                  ? "Install it in Control Center → Security → Malware scan (about 300 MB), then scan again."
                  : (report.summary || "") + (report.status === "found"
                     ? "\n\n" + report.findings.map(function (f) { return f.path + "\n   " + f.signature }).join("\n")
                     : report.status === "clean" ? "\nA scan finds known threats only: it isn't a guarantee." : "")
        standardButtons: Kirigami.Dialog.Close
        customFooterActions: [
            Kirigami.Action {
                text: "Move to quarantine"
                icon.name: "security-medium"
                visible: scanDialog.report.status === "found"
                onTriggered: {
                    var msgs = []
                    for (var i = 0; i < scanDialog.report.findings.length; i++) {
                        var f = scanDialog.report.findings[i]
                        msgs.push(backend.quarantineFile(f.path, f.signature).message)
                    }
                    scanDialog.close()
                    applicationWindow().notify(msgs.join(" "))
                }
            },
            Kirigami.Action {
                text: "Set up the scanner"
                icon.name: "security-high"
                visible: scanDialog.report.status === "no_scanner"
                onTriggered: { scanDialog.close(); backend.openSecurity() }
            }
        ]
    }

    // Right-click > Uninstall… (Windows games): what goes, with sizes,
    // measured in the background first.
    function sizeText(n) {
        return n >= 1073741824 ? (n / 1073741824).toFixed(1) + " GB" : Math.max(1, Math.round(n / 1048576)) + " MB"
    }
    Kirigami.Dialog {
        id: uninstallDialog
        property var info: ({})
        property bool measuring: true
        property bool working: false
        property string title_: ""
        function openFor(path, title) {
            info = {}
            title_ = title
            measuring = true
            working = false
            prefixBox.checked = true
            filesBox.checked = false
            savesBox.checked = true
            open()
            backend.uninstallInfo(path)
        }
        readonly property bool savesAtRisk: (info.saves || []).length > 0 && (prefixBox.checked || filesBox.checked)
        title: "Uninstall " + title_ + "?"
        preferredWidth: Kirigami.Units.gridUnit * 30
        padding: Kirigami.Units.largeSpacing * 2
        standardButtons: Kirigami.Dialog.Cancel
        customFooterActions: [
            Kirigami.Action {
                text: uninstallDialog.working ? "Uninstalling…" : "Uninstall"
                icon.name: "edit-delete"
                enabled: !uninstallDialog.measuring && !uninstallDialog.working && uninstallDialog.info.ok === true
                         && !uninstallDialog.info.running
                onTriggered: {
                    uninstallDialog.working = true
                    backend.uninstallGame("lutris:" + uninstallDialog.info.id, prefixBox.checked && prefixBox.visible,
                                          filesBox.checked && filesBox.visible, savesBox.checked)
                }
            }
        ]

        ColumnLayout {
            spacing: Kirigami.Units.largeSpacing

            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                visible: uninstallDialog.measuring
                text: "Checking how much space it takes…"
                opacity: 0.75
            }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                visible: !uninstallDialog.measuring
                text: uninstallDialog.info.ok === false ? uninstallDialog.info.message
                      : uninstallDialog.info.running ? uninstallDialog.title_ + " is running. Close it first, then uninstall it."
                      : "Always removed: the game from your library and from Lutris, its box art and its ReyOS settings."
                color: uninstallDialog.info.running || uninstallDialog.info.ok === false ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
            }
            Controls.CheckBox {
                id: prefixBox
                Layout.fillWidth: true
                visible: !uninstallDialog.measuring && !!uninstallDialog.info.prefix
                text: (uninstallDialog.info.installedInPrefix ? "Delete the installed game and its Windows folder ("
                                                              : "Delete its Windows folder (Wine prefix, ")
                      + sizeText(uninstallDialog.info.prefixSize || 0) + ")"
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: uninstallDialog.info.prefix || ""
            }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                visible: !uninstallDialog.measuring && !!uninstallDialog.info.prefixShared
                text: "Its Windows folder is shared with another game, so it stays."
                opacity: 0.75
            }
            Controls.CheckBox {
                id: filesBox
                Layout.fillWidth: true
                visible: !uninstallDialog.measuring && !!uninstallDialog.info.gameDir
                text: "Also delete the game files (" + sizeText(uninstallDialog.info.gameDirSize || 0) + ")"
            }
            Controls.Label {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.gridUnit * 2
                visible: filesBox.visible
                wrapMode: Text.WrapAnywhere
                text: (uninstallDialog.info.gameDir || "").replace(/^\/home\/[^\/]+/, "~")
                opacity: 0.7
            }
            Controls.CheckBox {
                id: savesBox
                Layout.fillWidth: true
                visible: !uninstallDialog.measuring && uninstallDialog.savesAtRisk
                text: "Keep my saves (copied to " + (uninstallDialog.info.savesDir || "").replace(/^\/home\/[^\/]+/, "~") + ")"
            }
            Controls.Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                visible: savesBox.visible && !savesBox.checked
                text: "Saves kept in the game's Windows folder or game folder are deleted with it."
                color: Kirigami.Theme.neutralTextColor
            }
        }
    }

    Connections {
        target: backend
        function onGamesChanged() { reload() }
        function onUninstallInfoReady(info) {
            uninstallDialog.info = info
            uninstallDialog.measuring = false
        }
        function onUninstallFinished(ok, text) {
            uninstallDialog.close()
            applicationWindow().notify(text, ok)
        }
        function onGameScanFinished(report) {
            gameScanning = false
            scanDialog.report = report
            scanDialog.open()
        }
        function onPcAddFinished(ok, text, path) {
            adding = false
            if (text === "") return  // cancelled in a dialog
            if (ok) { filterChosen = true; gameFilter = "pc" }
            pcAddDialog.ok = ok
            pcAddDialog.path = path
            pcAddDialog.subtitle = text
            pcAddDialog.open()
        }
        function onAddProgress(text, percent) {
            addText = text
            addPercent = percent
        }
        function onAddFinished(ok, text, originals) {
            adding = false
            if (text === "") return  // cancelled in the file picker
            addOriginals = originals
            addResult.type = ok ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            addResult.text = text + (originals.length > 0 ? " You can delete the original files now; the game stays in the library." : "")
            addResult.visible = true
        }
        function onCoverReady(path, cover) {
            for (var i = 0; i < allGames.length; i++)
                if (allGames[i].path === path) allGames[i].cover = cover
            for (var j = 0; j < gameModel.count; j++)
                if (gameModel.get(j).path === path) gameModel.setProperty(j, "cover", cover)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.largeSpacing

        // Adding a game: unpack, shrink, check. Takes a few minutes per game.
        ColumnLayout {
            visible: adding
            Layout.fillWidth: true
            Controls.Label {
                Layout.fillWidth: true
                text: addText
                wrapMode: Text.Wrap
            }
            // Not Controls.ProgressBar: under the KDE style it repaints the
            // window nonstop (see ReyOSProgressBar.qml).
            ReyOSProgressBar {
                Layout.fillWidth: true
                from: 0
                to: 100
                value: Math.max(0, addPercent)
                indeterminate: addPercent < 0
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: unconfiguredPad !== null
            type: Kirigami.MessageType.Information
            text: unconfiguredPad ? unconfiguredPad.name + " isn't set up for games yet." : ""
            actions: [
                Kirigami.Action {
                    text: "Set up"
                    icon.name: "input-gamepad"
                    onTriggered: setUpController(unconfiguredPad)
                }
            ]
        }

        Kirigami.InlineMessage {
            id: addResult
            Layout.fillWidth: true
            visible: false
            showCloseButton: true
            actions: [
                Kirigami.Action {
                    text: "Delete original files"
                    icon.name: "edit-delete"
                    visible: addOriginals.length > 0
                    onTriggered: {
                        var n = backend.deleteOriginals(addOriginals)
                        applicationWindow().notify(n + (n === 1 ? " original file deleted." : " original files deleted."))
                        addOriginals = []
                        addResult.text = n + (n === 1 ? " original file deleted." : " original files deleted.")
                    }
                }
            ]
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
            Kirigami.SearchField {
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                placeholderText: "Search games..."
                onTextChanged: gameSearch = text
            }
            Controls.Switch {
                text: "Download box art"
                checked: boxart
                onToggled: {
                    boxart = checked
                    backend.setBoxart(checked)
                    applicationWindow().notify(checked ? "Box art downloads are on." : "Box art downloads are off.")
                    if (checked) backend.fetchCovers()
                }
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Looks up covers by game name on thumbnails.libretro.com. Your own cover image with the same name as the game (next to it, or in ~/Games/Covers/<system>/) is always used first."
            }
        }

        // All, Windows games, Emulators.
        Controls.TabBar {
            id: systemTabs
            visible: allGames.length > 0 && gameSearch === ""
            Layout.fillWidth: true
            Repeater {
                model: gameTabs
                Controls.TabButton {
                    text: modelData.label
                    width: implicitWidth
                    onClicked: { filterChosen = true; gameFilter = modelData.id }
                }
            }
        }

        // Emulators: every console, or one picked here.
        RowLayout {
            visible: gameSearch === "" && consoleSystems.length > 1 && tabFilter === "emu"
            spacing: Kirigami.Units.largeSpacing
            Controls.Label { text: "Console:" }
            Controls.ComboBox {
                id: consolePicker
                Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                model: [{ id: "emu", label: "All consoles  " + consoleTotal }].concat(consoleSystems)
                textRole: "label"
                onActivated: function (i) { filterChosen = true; gameFilter = model[i].id }
            }
        }

        Kirigami.PlaceholderMessage {
            visible: allGames.length === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon.name: "input-gaming"
            text: "No games yet"
            explanation: systems.some(function (s) { return s.installed })
                         ? "Press Add games to add PlayStation 2, PSP or PlayStation games, or put games in the folder for their system under ~/Games/ROMs (for example ~/Games/ROMs/n64/), then press Refresh. Windows games: Add PC game."
                         : "First pick the systems you want to play in Control Center > Gaming, then put your games under ~/Games/ROMs."
            helpfulAction: Kirigami.Action {
                text: systems.some(function (s) { return s.installed }) ? "Open games folder" : "Set up emulators"
                icon.name: systems.some(function (s) { return s.installed }) ? "folder-open" : "configure"
                onTriggered: systems.some(function (s) { return s.installed }) ? backend.openGamesFolder("") : backend.openSetup()
            }
        }

        // In an Item that takes the free space: the message alone doesn't
        // grow, and the layout then spread the rows above it apart.
        Item {
            visible: allGames.length > 0 && gameModel.count === 0 && gameSearch === "" && gameFilter === "pc"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                width: parent.width - Kirigami.Units.gridUnit * 4
                icon.name: "applications-games"
                text: "No Windows games yet"
                explanation: "Add a game's installer (setup.exe) or the .exe of a game that's already installed. ReyOS sets up Lutris and Proton for you, with GameMode, the overlay and the right graphics card."
                helpfulAction: Kirigami.Action {
                    text: "Add PC game…"
                    icon.name: "list-add"
                    enabled: !adding
                    onTriggered: addPcGame()
                }
            }
        }

        Controls.Label {
            visible: allGames.length > 0 && gameModel.count === 0 && !(gameSearch === "" && gameFilter === "pc")
            Layout.fillWidth: true
            opacity: 0.7
            text: gameSearch !== "" ? "No games match \"" + gameSearch + "\"." : "No games here."
        }

        GridView {
            id: grid
            visible: gameModel.count > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: gameModel
            readonly property int columns: Math.max(1, Math.floor(width / (Kirigami.Units.gridUnit * 10)))
            cellWidth: Math.floor(width / columns)
            cellHeight: cellWidth * 1.25 + Kirigami.Units.gridUnit * 4
            Controls.ScrollBar.vertical: Controls.ScrollBar {}

            delegate: Item {
                width: grid.cellWidth
                height: grid.cellHeight

                Rectangle {
                    id: card
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.smallSpacing
                    radius: Kirigami.Units.cornerRadius
                    color: hover.containsMouse ? Kirigami.Theme.hoverColor : Kirigami.Theme.alternateBackgroundColor
                    opacity: model.playable ? 1 : 0.6

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Kirigami.Units.smallSpacing
                        spacing: Kirigami.Units.smallSpacing

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: width * 1.25

                            // Placeholder until (or unless) box art is found.
                            Rectangle {
                                anchors.fill: parent
                                radius: Kirigami.Units.cornerRadius
                                visible: cover.status !== Image.Ready
                                color: Kirigami.Theme.backgroundColor
                                border.color: Kirigami.Theme.disabledTextColor
                                border.width: 1
                                ColumnLayout {
                                    anchors.centerIn: parent
                                    width: parent.width - Kirigami.Units.largeSpacing * 2
                                    Controls.Label {
                                        Layout.alignment: Qt.AlignHCenter
                                        text: model.short
                                        font.bold: true
                                        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 2
                                        color: Kirigami.Theme.highlightColor
                                    }
                                    Controls.Label {
                                        Layout.fillWidth: true
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 4
                                        elide: Text.ElideRight
                                        text: model.title
                                        opacity: 0.8
                                    }
                                }
                            }
                            Image {
                                id: cover
                                anchors.fill: parent
                                source: model.cover ? "file://" + model.cover : ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                sourceSize.width: width * 2
                                smooth: true
                            }
                            // Text, not a theme icon: "window" isn't in every icon
                            // theme and drew nothing on the ReyOS theme.
                            Rectangle {
                                visible: model.windowed
                                anchors.top: parent.top
                                anchors.right: parent.right
                                anchors.margins: Kirigami.Units.smallSpacing
                                width: windowedLabel.implicitWidth + Kirigami.Units.largeSpacing
                                height: windowedLabel.implicitHeight + Kirigami.Units.smallSpacing
                                radius: height / 2
                                color: Qt.rgba(0, 0, 0, 0.7)
                                Controls.Label {
                                    id: windowedLabel
                                    anchors.centerIn: parent
                                    text: "In a window"
                                    color: "white"
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                }
                            }
                            Rectangle {
                                anchors.centerIn: parent
                                width: Kirigami.Units.iconSizes.huge
                                height: width
                                radius: width / 2
                                color: Qt.rgba(0, 0, 0, 0.55)
                                visible: hover.containsMouse && model.playable
                                Kirigami.Icon {
                                    anchors.centerIn: parent
                                    width: Kirigami.Units.iconSizes.medium
                                    height: width
                                    source: "media-playback-start"
                                    color: "white"
                                }
                            }
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            text: model.title
                            font.bold: true
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            visible: !model.playable || (consoleFilter === "" && gameFilter !== "pc") || gameSearch !== ""
                            text: model.playable ? model.system.replace(/ \(needs a fast PC\)/, "") : "Emulator not installed"
                            opacity: 0.7
                            elide: Text.ElideRight
                        }
                    }

                    MouseArea {
                        id: hover
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        cursorShape: model.playable ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton) gameMenu.popup()
                            else if (model.playable) backend.launchGame(model.systemId, model.path)
                        }
                        onPressAndHold: gameMenu.popup()
                    }
                    Controls.Menu {
                        id: gameMenu
                        // Systems without a 3D resolution (NES, SNES...) don't get the submenu.
                        Component.onCompleted: {
                            if (!model.has3d) removeMenu(resolutionMenu)
                            if (!model.nvidiaAvailable) removeMenu(gpuMenu)
                        }
                        width: Kirigami.Units.gridUnit * 17
                        Controls.MenuItem {
                            text: "Play"
                            icon.name: "media-playback-start"
                            enabled: model.playable
                            onTriggered: backend.launchGame(model.systemId, model.path)
                        }
                        Controls.MenuItem {
                            // Hidden (no height) for games that are already shrunk.
                            visible: model.shrinkable
                            height: visible ? implicitHeight : 0
                            text: "Shrink to save space"
                            icon.name: "package-x-generic"
                            enabled: !adding
                            onTriggered: shrinkGame(model.path, model.title)
                        }
                        Controls.Menu {
                            id: resolutionMenu
                            title: "3D resolution" + (model.resolution > 0 ? ": " + resolutionNames[model.resolution] : "")
                            enabled: model.resolutionSettable
                            Controls.MenuItem {
                                text: "Same as Control Center (" + resolutionNames[defaultResolution] + ")"
                                checkable: true
                                checked: model.resolution === 0
                                onTriggered: setResolution(index, model.path, 0)
                            }
                            Controls.MenuSeparator {}
                            Controls.MenuItem { text: "Original (fastest)"; checkable: true; checked: model.resolution === 1; onTriggered: setResolution(index, model.path, 1) }
                            Controls.MenuItem { text: "2×"; checkable: true; checked: model.resolution === 2; onTriggered: setResolution(index, model.path, 2) }
                            Controls.MenuItem { text: "3×"; checkable: true; checked: model.resolution === 3; onTriggered: setResolution(index, model.path, 3) }
                            Controls.MenuItem { text: "4× (sharpest)"; checkable: true; checked: model.resolution === 4; onTriggered: setResolution(index, model.path, 4) }
                        }
                        // PC (Windows) games: graphics card and Lutris
                        // instead of console buttons and the window switch.
                        Controls.Menu {
                            id: gpuMenu
                            width: Kirigami.Units.gridUnit * 19
                            title: "Graphics card" + (model.gpu !== "" ? ": " + gpuNames[model.gpu] : "")
                            Controls.MenuItem {
                                text: "Same as Control Center (" + gpuNames[defaultGpu] + ")"
                                checkable: true
                                checked: model.gpu === ""
                                onTriggered: setGpu(index, model.path, "")
                            }
                            Controls.MenuSeparator {}
                            Controls.MenuItem { text: "NVIDIA graphics card (faster)"; checkable: true; checked: model.gpu === "nvidia"; onTriggered: setGpu(index, model.path, "nvidia") }
                            Controls.MenuItem { text: "Built-in graphics (cooler, longer battery)"; checkable: true; checked: model.gpu === "builtin"; onTriggered: setGpu(index, model.path, "builtin") }
                        }
                        Controls.MenuItem {
                            visible: model.systemId === "pc"
                            height: visible ? implicitHeight : 0
                            text: gameScanning ? "Scanning for viruses…" : "Scan for viruses"
                            icon.name: "security-high"
                            enabled: !gameScanning
                            onTriggered: {
                                gameScanning = true
                                applicationWindow().notify("Scanning " + model.title + " for viruses… this can take a few minutes.")
                                backend.scanGame(model.path)
                            }
                        }
                        Controls.MenuItem {
                            visible: model.systemId === "pc"
                            height: visible ? implicitHeight : 0
                            text: "Open in Lutris (more settings)"
                            icon.name: "configure"
                            onTriggered: backend.openLutris()
                        }
                        // Old Ubisoft games only take the pads on their own list.
                        Controls.MenuItem {
                            visible: model.gamepadList === true
                            height: visible ? implicitHeight : 0
                            text: "Let any controller work"
                            icon.name: "input-gamepad"
                            onTriggered: {
                                var r = backend.turnOffGamepadList(model.path)
                                applicationWindow().notify(r.message, r.ok)
                                if (r.ok) gameModel.setProperty(index, "gamepadList", false)
                            }
                        }
                        Controls.MenuItem {
                            text: "Controller buttons…"
                            icon.name: "input-gamepad"
                            onTriggered: buttonsDialog.openFor(model.systemId)
                        }
                        Controls.MenuItem {
                            visible: model.systemId === "pc"
                            height: visible ? implicitHeight : 0
                            text: "Uninstall…"
                            icon.name: "edit-delete"
                            onTriggered: uninstallDialog.openFor(model.path, model.title)
                        }
                        // Not for PC games: Proton's virtual desktop fills the
                        // screen anyway (tested); a real window needs gamescope.
                        Controls.MenuItem {
                            visible: model.systemId !== "pc"
                            height: visible ? implicitHeight : 0
                            text: "Always play this game in a window"
                            checkable: true
                            checked: model.windowed
                            onToggled: {
                                backend.setGameWindowed(model.path, checked)
                                applicationWindow().notify(checked ? model.title + " will open in a window." : model.title + " no longer opens in a window.")
                                gameModel.setProperty(index, "windowed", checked)
                                // Keep the unfiltered list in step, or the badge
                                // would vanish on the next search/filter change.
                                for (var i = 0; i < allGames.length; i++)
                                    if (allGames[i].path === model.path) allGames[i].windowed = checked
                            }
                        }
                    }
                }
            }
        }
    }
}
