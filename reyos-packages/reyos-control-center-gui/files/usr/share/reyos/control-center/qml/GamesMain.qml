import QtQuick
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: gamesWindow
    title: "ReyOS Games"
    width: Kirigami.Units.gridUnit * 60
    height: Kirigami.Units.gridUnit * 40
    minimumWidth: Kirigami.Units.gridUnit * 24
    minimumHeight: Kirigami.Units.gridUnit * 20

    pageStack.initialPage: GameLibraryPage {}
    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.ToolBar

    // Same change popup as Control Center.
    function notify(message, ok) { changePopup.show(message, ok) }

    ReyOSChangePopup { id: changePopup }

    Connections {
        target: backend
        function onMessage(ok, text) { gamesWindow.notify(text, ok) }
    }
}
