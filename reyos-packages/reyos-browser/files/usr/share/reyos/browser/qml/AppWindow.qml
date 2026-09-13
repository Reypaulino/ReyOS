import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine

ApplicationWindow {
    id: appWindow
    width: 1100
    height: 720
    minimumWidth: 480
    minimumHeight: 360
    visible: true
    color: "#15110E"
    title: (view.lifecycleState === WebEngineView.LifecycleState.Frozen ? "❄ " : (view.lifecycleState === WebEngineView.LifecycleState.Discarded ? "◌ " : "")) + (view.title && view.title.length ? view.title : appTitle)

    function updateLifecycle() {
        if (!browserBackend.lowMemoryMode || appWindow.active) {
            lifecycleTimer.stop()
            view.lifecycleState = WebEngineView.LifecycleState.Active
            return
        }
        lifecycleTimer.restart()
    }

    onActiveChanged: updateLifecycle()
    Component.onCompleted: updateLifecycle()

    Connections {
        target: browserBackend
        function onLowMemoryChanged() { appWindow.updateLifecycle() }
    }

    Timer {
        id: lifecycleTimer
        interval: view.lifecycleState === WebEngineView.LifecycleState.Active ? 120000 : 480000
        repeat: false
        onTriggered: {
            if (appWindow.active || !browserBackend.lowMemoryMode) {
                return
            }
            if (view.lifecycleState === WebEngineView.LifecycleState.Active) {
                if (view.recommendedState !== WebEngineView.LifecycleState.Active) {
                    view.lifecycleState = WebEngineView.LifecycleState.Frozen
                }
                lifecycleTimer.restart()
            } else if (view.lifecycleState === WebEngineView.LifecycleState.Frozen && view.recommendedState === WebEngineView.LifecycleState.Discarded) {
                view.lifecycleState = WebEngineView.LifecycleState.Discarded
            }
        }
    }

    WebEngineProfile {
        id: appProfile
        objectName: "appProfile"
        storageName: appStorageName
        persistentCookiesPolicy: WebEngineProfile.AllowPersistentCookies
        httpCacheType: WebEngineProfile.DiskHttpCache
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ToolBar {
            Layout.fillWidth: true
            implicitHeight: 34
            background: Rectangle { color: "#302217" }
            contentItem: RowLayout {
                spacing: 3
                Item { Layout.fillWidth: true }
                ToolButton {
                    id: memoryButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-memory.svg")
                    icon.width: 16
                    icon.height: 16
                    implicitWidth: 28
                    implicitHeight: 28
                    opacity: browserBackend.lowMemoryMode ? 1.0 : 0.5
                    background: Rectangle { color: memoryButton.hovered ? "#3B291C" : "transparent"; radius: 6 }
                    onClicked: browserBackend.toggleLowMemoryMode()
                    ToolTip.visible: hovered
                    ToolTip.text: browserBackend.lowMemoryMode ? "Low Memory Mode: On" : "Low Memory Mode: Off"
                    Accessible.name: "Low Memory Mode"
                }
                ToolButton {
                    id: shieldsButton
                    icon.source: Qt.resolvedUrl("../icons/reyos-shields.svg")
                    icon.width: 18
                    icon.height: 18
                    implicitWidth: 28
                    implicitHeight: 28
                    opacity: browserBackend.shieldsEnabled ? 1.0 : 0.5
                    background: Rectangle { color: shieldsButton.hovered ? "#3B291C" : "transparent"; radius: 6 }
                    onClicked: siteSafetyDialog.open()
                    ToolTip.visible: hovered
                    ToolTip.text: "Site Safety"
                    Accessible.name: "Site Safety"
                }
            }
        }

        WebEngineView {
            id: view
            Layout.fillWidth: true
            Layout.fillHeight: true
            profile: appProfile
            url: appUrl
            userScripts.collection: [
                {
                    name: "reyos-fingerprint-protection",
                    sourceCode: browserBackend.fingerprintScriptSource,
                    injectionPoint: WebEngineScript.DocumentCreation,
                    worldId: WebEngineScript.MainWorld,
                    runsOnSubFrames: true
                }
            ]
            settings.javascriptCanOpenWindows: false
            settings.pdfViewerEnabled: true
            settings.pluginsEnabled: true
            onUrlChanged: browserBackend.setCurrentSite(url.toString())
        }
    }

    Dialog {
        id: siteSafetyDialog
        title: "Site Safety"
        modal: true
        width: 450
        anchors.centerIn: parent
        padding: 18
        background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 12 }
        contentItem: ColumnLayout {
            spacing: 12
            Label {
                text: browserBackend.currentSite.length ? browserBackend.currentSite : appTitle
                font.bold: true
                font.pixelSize: 18
                color: "#FFF3E6"
                Layout.fillWidth: true
                elide: Text.ElideMiddle
            }
            Label {
                text: view.url.scheme === "https" ? "Connection: Secure HTTPS" : "Connection: Not secure — this page does not use HTTPS"
                wrapMode: Text.Wrap
                color: view.url.scheme === "https" ? "#9AD8AE" : "#F0B46A"
                Layout.fillWidth: true
            }
            Label {
                text: "Site permission requests (camera, location, etc.) aren't supported in installed apps yet."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#8E5A2E" }
            Label {
                text: "ReyOS Shields: " + (browserBackend.shieldsEnabled ? "On" : "Off") + " · " + browserBackend.blockedRequestCount + " requests blocked this session"
                wrapMode: Text.Wrap
                color: "#F4D5A8"
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: browserBackend.shieldsEnabled ? "Turn Shields Off" : "Turn Shields On"
                    onClicked: browserBackend.toggleShields()
                }
                Button {
                    visible: browserBackend.currentSite.length > 0
                    text: browserBackend.currentSiteShieldsEnabled ? "Disable for this site" : "Enable for this site"
                    onClicked: browserBackend.toggleCurrentSiteShields()
                }
            }
            Label {
                text: "This app keeps its own sign-in and session data, so you stay logged in between launches."
                wrapMode: Text.Wrap
                color: "#D7C1AA"
                Layout.fillWidth: true
            }
            Button { text: "Close"; Layout.alignment: Qt.AlignRight; onClicked: siteSafetyDialog.close() }
        }
    }

    Shortcut { sequence: "Alt+Left"; onActivated: if (view.canGoBack) view.goBack() }
    Shortcut { sequence: StandardKey.Back; onActivated: if (view.canGoBack) view.goBack() }
    Shortcut { sequence: "Alt+Right"; onActivated: if (view.canGoForward) view.goForward() }
    Shortcut { sequence: StandardKey.Forward; onActivated: if (view.canGoForward) view.goForward() }
    Shortcut { sequence: StandardKey.Refresh; onActivated: view.reload() }
    Shortcut { sequence: StandardKey.Quit; onActivated: Qt.quit() }
}
