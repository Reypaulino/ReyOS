import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Connect"
    width: 980
    height: 720
    minimumWidth: 520
    minimumHeight: 480

    property bool backendAvailable: false
    property bool kdeconnectInstalled: true
    property var diagnostics: ({})
    property string section: "devices"

    readonly property var sectionPages: ({
        "devices": "DevicesPage.qml",
        "remote-desktop": "RemoteDesktopPage.qml",
        "vpn": "RemoteAccessPage.qml",
        "bluetooth": "BluetoothPage.qml",
        "diagnostics": "DiagnosticsPage.qml"
    })

    function openSection(name) {
        section = name
        pageStack.clear()
        pageStack.push(Qt.resolvedUrl(sectionPages[name]))
        if (globalDrawer.modal) globalDrawer.close()
    }

    function openDevice(deviceId) {
        if (section !== "devices") openSection("devices")
        while (pageStack.depth > 1) pageStack.pop()
        pageStack.push(Qt.resolvedUrl("DeviceDetailPage.qml"), {deviceId: deviceId})
    }

    function askFirewall() { confirmFirewall.open() }

    pageStack.columnView.columnResizeMode: Kirigami.ColumnView.SingleColumn
    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.ToolBar
    pageStack.globalToolBar.showNavigationButtons: Kirigami.ApplicationHeaderStyle.ShowBackButton

    Connections {
        target: backend
        function onBackendAvailableChanged(available) { backendAvailable = available }
        function onDiagnosticsReady(info) { diagnostics = info }
        function onActionFinished(ok, message) { if (message) showPassiveNotification(message) }
        function onPairingFailedSignal(deviceId, error) { showPassiveNotification("Pairing failed: " + error, "long") }
        function onFileReceived(deviceId, path) {
            showPassiveNotification("Received " + (path.split("/").pop() || "a file"), "long", "Open Folder",
                                    function() { backend.openContainingFolder(path) })
        }
    }

    Component.onCompleted: {
        kdeconnectInstalled = backend.isKdeconnectInstalled()
        backendAvailable = backend.isDaemonRunning()
        backend.refreshDiagnostics()
        openSection("devices")
    }

    globalDrawer: Kirigami.GlobalDrawer {
        id: drawer
        modal: !appWindow.wideScreen
        drawerOpen: !modal
        handleVisible: modal
        isMenu: false
        width: Kirigami.Units.gridUnit * 13

        header: RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Kirigami.Icon {
                source: "org.reyos.Connect"
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                Layout.leftMargin: Kirigami.Units.largeSpacing
                Layout.topMargin: Kirigami.Units.largeSpacing
                Layout.bottomMargin: Kirigami.Units.largeSpacing
            }
            ColumnLayout {
                spacing: 0
                Kirigami.Heading { text: "ReyOS Connect"; level: 4 }
                Controls.Label {
                    text: !kdeconnectInstalled ? "KDE Connect missing" : backendAvailable ? "Ready" : "Service stopped"
                    color: backendAvailable ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }
            }
        }

        actions: [
            Kirigami.Action {
                text: "Devices"
                icon.name: "smartphone"
                checkable: true
                checked: appWindow.section === "devices"
                onTriggered: openSection("devices")
            },
            Kirigami.Action {
                text: "Remote Desktop"
                icon.name: "computer"
                checkable: true
                checked: appWindow.section === "remote-desktop"
                onTriggered: openSection("remote-desktop")
            },
            Kirigami.Action {
                text: "VPN"
                icon.name: "network-vpn"
                checkable: true
                checked: appWindow.section === "vpn"
                onTriggered: openSection("vpn")
            },
            Kirigami.Action {
                text: "Bluetooth"
                icon.name: "network-bluetooth"
                checkable: true
                checked: appWindow.section === "bluetooth"
                onTriggered: openSection("bluetooth")
            },
            Kirigami.Action {
                text: "Diagnostics"
                icon.name: "system-search"
                checkable: true
                checked: appWindow.section === "diagnostics"
                onTriggered: openSection("diagnostics")
            }
        ]
    }

    Controls.Dialog {
        id: confirmFirewall
        title: "Allow KDE Connect through the firewall?"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        width: Math.min(Kirigami.Units.gridUnit * 26, appWindow.width - Kirigami.Units.gridUnit * 2)
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: backend.openFirewallForKdeConnect()
        Controls.Label {
            width: parent.width
            wrapMode: Text.Wrap
            text: "This opens ports 1714-1764 (TCP and UDP) — the range KDE Connect itself needs to discover and talk to your devices. No other ports are affected."
        }
    }
}
