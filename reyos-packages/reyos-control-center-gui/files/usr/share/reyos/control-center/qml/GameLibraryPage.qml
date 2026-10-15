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

    // Systems that have games, for the picker.
    property var gameSystems: {
        var list = [{ id: "", label: "All systems (" + allGames.length + ")" }]
        for (var i = 0; i < systems.length; i++)
            if (systems[i].games > 0)
                list.push({ id: systems[i].id, label: systems[i].name + " (" + systems[i].games + ")" })
        return list
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
        applicationWindow().showPassiveNotification(value === 0 ? "This game follows Control Center's 3D resolution again."
                                                   : "3D resolution for this game: " + resolutionNames[value] + ". It applies the next time you start it.")
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
            text: "Controller…"
            icon.name: "input-gamepad"
            tooltip: "Set up your controller's buttons for games (opens Control Center)."
            onTriggered: backend.setUpController()
        },
        Kirigami.Action {
            text: "Set up emulators"
            icon.name: "configure"
            onTriggered: backend.openSetup()
        },
        Kirigami.Action {
            text: "Open games folder"
            icon.name: "folder-open"
            onTriggered: backend.openGamesFolder(gameFilter)
        },
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: { gamesSignature = ""; reload() }
        }
    ]

    property string gamesSignature: ""

    function reload() {
        var games = backend.emulationGames()
        // Only rebuild the grid when something changed, so a focus-change
        // rescan doesn't lose the scroll position.
        var sig = JSON.stringify(games.map(function (g) { return [g.path, g.playable, g.cover] }))
        systems = backend.emulationSystems()
        controllers = backend.controllers()
        defaultResolution = backend.defaultResolution()
        boxart = backend.boxartEnabled()
        if (sig !== gamesSignature) {
            gamesSignature = sig
            allGames = games
            if (!gameSystems.some(function (s) { return s.id === gameFilter })) gameFilter = ""
            applyFilter()
        }
        backend.fetchCovers()
    }

    function applyFilter() {
        gameModel.clear()
        var q = gameSearch.toLowerCase()
        for (var i = 0; i < allGames.length; i++) {
            var g = allGames[i]
            if ((gameFilter === "" || g.systemId === gameFilter)
                    && (q === "" || g.title.toLowerCase().indexOf(q) >= 0))
                gameModel.append(g)
        }
    }

    onGameFilterChanged: applyFilter()
    onGameSearchChanged: applyFilter()
    Component.onCompleted: {
        reload()
        var start = backend.startWith()
        if (start === "add") addGames()
        else if (start === "shrink" && !adding) {
            startAdding("Shrinking your games...")
            backend.shrinkAll()
        }
    }

    // Also rescan when the window comes back to the front (a game added
    // while it was open in the background, or an emulator just installed).
    Connections {
        target: libraryPage.Window.window
        function onActiveChanged() { if (libraryPage.Window.window.active) reload() }
    }

    ListModel { id: gameModel }

    // A system's buttons: what each console button is on your controller,
    // changed here (a swap, so nothing is doubled). Same settings as
    // Control Center > Gaming > Button layout.
    Controls.Dialog {
        id: buttonsDialog
        property string systemId: ""
        property var layout: ({})
        property string activeKey: ""
        function openFor(id) {
            systemId = id
            layout = backend.buttonLayout(id)
            activeKey = ""
            open()
        }
        function changed() { layout = backend.buttonLayout(systemId) }
        title: "Controller buttons: " + (layout.name || "")
        modal: true
        parent: Controls.Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 40)
        height: Math.min(parent.height - Kirigami.Units.gridUnit * 2, implicitHeight)
        standardButtons: Controls.Dialog.Close
        contentItem: Controls.ScrollView {
            contentWidth: availableWidth
            ColumnLayout {
                width: buttonsDialog.availableWidth
                spacing: Kirigami.Units.largeSpacing
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.7
                    text: (buttonsDialog.layout.rows || []).length === 0 ? "No controller layout for this system."
                          : "Which button on your controller does each " + buttonsDialog.layout.pad + " button. Pick another to swap the two. It applies the next time you start a game."
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: buttonsDialog.availableWidth > Kirigami.Units.gridUnit * 30 ? 2 : 1
                    columnSpacing: Kirigami.Units.gridUnit
                    ControllerDiagram {
                        Layout.alignment: Qt.AlignTop | Qt.AlignHCenter
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                        Layout.preferredHeight: Layout.preferredWidth * 200 / 320
                        brand: buttonsDialog.layout.brand || "generic"
                        overrides: buttonsDialog.layout.labels || ({})
                        activeKey: buttonsDialog.activeKey
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: 0
                        Repeater {
                            model: buttonsDialog.layout.rows || []
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                Controls.Label {
                                    text: modelData.console
                                    font.bold: true
                                    Layout.preferredWidth: Kirigami.Units.gridUnit * 7
                                    elide: Text.ElideRight
                                }
                                Controls.Label { text: "→"; opacity: 0.6 }
                                Controls.Label {
                                    visible: !modelData.movable
                                    text: modelData.yours
                                    Layout.fillWidth: true
                                }
                                Controls.ComboBox {
                                    visible: modelData.movable
                                    wheelEnabled: false
                                    Layout.fillWidth: true
                                    model: buttonsDialog.layout.choices || []
                                    textRole: "label"
                                    currentIndex: Math.max(0, (buttonsDialog.layout.choices || []).findIndex(function (c) { return c.key === modelData.pad }))
                                    onActivated: {
                                        backend.setButton(buttonsDialog.systemId, modelData.key, buttonsDialog.layout.choices[currentIndex].key)
                                        buttonsDialog.activeKey = buttonsDialog.layout.choices[currentIndex].key
                                        buttonsDialog.changed()
                                    }
                                    onHoveredChanged: if (hovered) buttonsDialog.activeKey = modelData.pad
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
                }
                Controls.Button {
                    visible: buttonsDialog.layout.custom === true
                    text: "Back to the usual layout"
                    icon.name: "edit-undo"
                    onClicked: { backend.resetButtons(buttonsDialog.systemId); buttonsDialog.changed() }
                }
            }
        }
    }

    Connections {
        target: backend
        function onGamesChanged() { reload() }
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
                    onTriggered: backend.setUpController()
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
                        addOriginals = []
                        addResult.text = n + (n === 1 ? " original file deleted." : " original files deleted.")
                    }
                }
            ]
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.largeSpacing
            Controls.ComboBox {
                Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                model: gameSystems
                textRole: "label"
                valueRole: "id"
                currentIndex: Math.max(0, gameSystems.findIndex(function (s) { return s.id === gameFilter }))
                onActivated: gameFilter = currentValue
            }
            Kirigami.SearchField {
                Layout.fillWidth: true
                placeholderText: "Search games..."
                onTextChanged: gameSearch = text
            }
            Controls.Switch {
                text: "Download box art"
                checked: boxart
                onToggled: {
                    boxart = checked
                    backend.setBoxart(checked)
                    if (checked) backend.fetchCovers()
                }
                Controls.ToolTip.visible: hovered
                Controls.ToolTip.text: "Looks up covers by game name on thumbnails.libretro.com. Your own cover image with the same name as the game (next to it, or in ~/Games/Covers/<system>/) is always used first."
            }
        }

        Kirigami.PlaceholderMessage {
            visible: allGames.length === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon.name: "input-gaming"
            text: "No games yet"
            explanation: systems.some(function (s) { return s.installed })
                         ? "Press Add games to add PlayStation 2, PSP or PlayStation games, or put games in the folder for their system under ~/Games/ROMs (for example ~/Games/ROMs/n64/), then press Refresh."
                         : "First pick the systems you want to play in Control Center > Gaming, then put your games under ~/Games/ROMs."
            helpfulAction: Kirigami.Action {
                text: systems.some(function (s) { return s.installed }) ? "Open games folder" : "Set up emulators"
                icon.name: systems.some(function (s) { return s.installed }) ? "folder-open" : "configure"
                onTriggered: systems.some(function (s) { return s.installed }) ? backend.openGamesFolder("") : backend.openSetup()
            }
        }

        Controls.Label {
            visible: allGames.length > 0 && gameModel.count === 0
            Layout.fillWidth: true
            opacity: 0.7
            text: "No games match."
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
                            text: model.playable ? model.system : model.system + " — emulator not installed"
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
                        Component.onCompleted: if (!model.has3d) removeMenu(resolutionMenu)
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
                        Controls.MenuItem {
                            text: "Controller buttons for " + model.system + "…"
                            icon.name: "input-gamepad"
                            onTriggered: buttonsDialog.openFor(model.systemId)
                        }
                        Controls.MenuItem {
                            text: "Always play this game in a window"
                            checkable: true
                            checked: model.windowed
                            onToggled: {
                                backend.setGameWindowed(model.path, checked)
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
