import QtQuick
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Welcome"
    width: 780
    height: 560
    minimumWidth: 620
    minimumHeight: 460

    pageStack.initialPage: Qt.resolvedUrl("WelcomePage.qml")
    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.None
    // Without this, Kirigami's PageRow shows multiple wizard steps side-by-side
    // as columns whenever the window is wide enough (its default adaptive
    // multi-column behavior, meant for browser-style apps) -- this is a linear
    // wizard, each step should fully replace the previous one.
    pageStack.columnView.columnResizeMode: Kirigami.ColumnView.SingleColumn
}
