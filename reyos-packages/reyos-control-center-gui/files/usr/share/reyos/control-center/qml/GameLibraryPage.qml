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

    // Systems that have games, for the picker.
    property var gameSystems: {
        var list = [{ id: "", label: "All systems (" + allGames.length + ")" }]
        for (var i = 0; i < systems.length; i++)
            if (systems[i].games > 0)
                list.push({ id: systems[i].id, label: systems[i].name + " (" + systems[i].games + ")" })
        return list
    }

    actions: [
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
    Component.onCompleted: reload()

    // Also rescan when the window comes back to the front (a game added
    // while it was open in the background, or an emulator just installed).
    Connections {
        target: libraryPage.Window.window
        function onActiveChanged() { if (libraryPage.Window.window.active) reload() }
    }

    ListModel { id: gameModel }

    Connections {
        target: backend
        function onGamesChanged() { reload() }
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
                         ? "Put your games in the folder for their system under ~/Games/ROMs (for example ~/Games/ROMs/n64/), then press Refresh."
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
                        width: Kirigami.Units.gridUnit * 17
                        Controls.MenuItem {
                            text: "Play"
                            icon.name: "media-playback-start"
                            enabled: model.playable
                            onTriggered: backend.launchGame(model.systemId, model.path)
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
