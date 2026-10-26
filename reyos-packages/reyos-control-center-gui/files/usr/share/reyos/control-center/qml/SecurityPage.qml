import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Security"

    property bool busy: false
    property bool firewallEnabled: false
    property string vpnActive: ""
    property int vpnProfileCount: 0
    property int shieldsBlocked: 0
    property bool usbGuardEnabled: false
    // ReyOS Scan (malware scan with ClamAV)
    property var malware: ({ installed: false, last: {}, quarantineCount: 0, quickScope: [] })
    property bool malwareBusy: false     // installing / updating definitions
    property bool scanning: false
    property int scanFiles: 0
    property string scanPath: ""
    property string malwareNote: ""
    property bool malwareNoteOk: true
    readonly property var lastScan: malware.last || ({})
    readonly property var scanKinds: ({ quick: "Quick scan", home: "Full home scan", folder: "Folder scan",
                                        addgame: "check before adding a game", game: "game scan" })
    function refreshMalware() { malware = backend.malwareStatus() }
    function startScan(kind, folder) {
        scanning = true; scanFiles = 0; scanPath = ""; malwareNote = ""
        backend.startMalwareScan(kind, folder || "")
    }

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshSecurityOverview()
        backend.refreshUsbGuardStatus()
        refreshMalware()
    }

    Connections {
        target: backend
        function onSecurityOverviewReady(info) {
            busy = false
            firewallEnabled = info.firewallEnabled
            vpnActive = info.vpnActive || ""
            vpnProfileCount = info.vpnProfileCount
            shieldsBlocked = info.shieldsBlocked
        }
        function onUsbGuardStatusReady(info) {
            usbGuardEnabled = info.enabled
        }
        function onMalwareLog(line) { if (line.trim() !== "") scanPath = line.trim() }
        function onMalwareActionFinished(ok, message) {
            malwareBusy = false; scanPath = ""
            malwareNote = message; malwareNoteOk = ok
            refreshMalware()
        }
        function onMalwareProgress(files, path) { scanFiles = files; scanPath = path }
        function onMalwareScanFinished(report) {
            scanning = false; scanPath = ""
            refreshMalware()
        }
        function onPathBrowsed(target, path) {
            if (target === "malwareFolder" && path !== "") startScan("folder", path)
        }
        function onActionFinished(ok, message) {
            busy = false
            usbGuardStatusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            usbGuardStatusLabel.color = Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Controls.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: "How your computer is protected, at a glance."
        }

        GridLayout {
            Layout.fillWidth: true
            columns: parent.width > Kirigami.Units.gridUnit * 40 ? 3 : (parent.width > Kirigami.Units.gridUnit * 24 ? 2 : 1)
            columnSpacing: Kirigami.Units.gridUnit
            rowSpacing: Kirigami.Units.gridUnit

            Kirigami.AbstractCard {
                // Equal columns: without a shared preferred width a long
                // label widened one column and pushed the next card's
                // button past its border.
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "security-medium"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "Firewall"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: firewallEnabled ? "Active" : "Inactive"
                        color: firewallEnabled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                        font.bold: true
                    }
                    Controls.Button {
                        text: "Open Firewall"
                        Layout.alignment: Qt.AlignLeft
                        onClicked: applicationWindow().openReyosPage("FirewallPage.qml")
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "network-vpn"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "VPN"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: vpnActive.length > 0 ? ("Connected: " + vpnActive) : (vpnProfileCount > 0 ? "Not connected" : "No profiles imported")
                        color: vpnActive.length > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                    }
                    Controls.Button {
                        text: "Open VPN"
                        Layout.alignment: Qt.AlignLeft
                        onClicked: applicationWindow().openReyosPage("VpnPage.qml")
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "view-private"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "Browser Shields"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: shieldsBlocked > 0 ? (shieldsBlocked + " trackers and ads blocked in Reyva so far") : "No data yet — open Reyva"
                        color: shieldsBlocked > 0 ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "object-locked"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "Permissions"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: "File ownership & access fixes"
                        opacity: 0.7
                        wrapMode: Text.Wrap
                    }
                    Controls.Button {
                        text: "Open Permissions"
                        Layout.alignment: Qt.AlignLeft
                        onClicked: applicationWindow().openReyosPage("PermissionsPage.qml")
                    }
                }
            }

            Kirigami.AbstractCard {
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                padding: Kirigami.Units.gridUnit
                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Kirigami.Icon { source: "drive-removable-media-usb"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    Kirigami.Heading { text: "USB Protection"; level: 4 }
                    Controls.Label {
                        Layout.fillWidth: true
                        text: usbGuardEnabled ? "Blocking unrecognized USB devices" : "Off — any USB device is allowed"
                        color: usbGuardEnabled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                        wrapMode: Text.Wrap
                    }
                    Controls.Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        opacity: 0.7
                        text: "Guards against malicious USB devices (BadUSB). Off by default so plugging in a flash drive just works."
                    }
                    Controls.Button {
                        text: usbGuardEnabled ? "Disable USB protection" : "Enable USB protection"
                        Layout.alignment: Qt.AlignLeft
                        enabled: !busy
                        onClicked: {
                            busy = true
                            if (usbGuardEnabled) backend.disableUsbGuard()
                            else backend.enableUsbGuard()
                        }
                    }
                }
            }
        }

        // ReyOS Scan
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon { source: "security-high"; Layout.preferredWidth: Kirigami.Units.iconSizes.large; Layout.preferredHeight: Kirigami.Units.iconSizes.large }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Kirigami.Heading { text: "Malware scan"; level: 4 }
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            font.bold: true
                            text: !malware.installed ? "Not installed"
                                  : lastScan.status === undefined ? "No scan yet"
                                  : lastScan.summary + " (" + scanKinds[lastScan.kind] + ", " + new Date(lastScan.finished * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) + ")"
                            color: lastScan.status === "clean" ? Kirigami.Theme.positiveTextColor
                                 : lastScan.status === "found" ? Kirigami.Theme.negativeTextColor
                                 : malware.installed && lastScan.status !== undefined ? Kirigami.Theme.neutralTextColor
                                 : Kirigami.Theme.disabledTextColor
                        }
                        Controls.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            opacity: 0.75
                            visible: malware.installed
                            text: malware.definitions === "" ? "No virus definitions yet: press Update definitions."
                                  : "Virus definitions from " + malware.definitionsDate + (malware.ageDays > 7 ? " — out of date, update them" : "")
                            color: malware.definitions === "" || malware.ageDays > 7 ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
                        }
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    visible: !malware.installed
                    text: "Checks your files for known viruses and other malware with ClamAV, only when you ask. Installing it takes about 300 MB, with virus definitions that update themselves every day."
                }

                // Threats from the last scan: one row each, quarantine on request.
                Repeater {
                    model: lastScan.status === "found" ? lastScan.findings : []
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Kirigami.Icon { source: "dialog-warning"; Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium; Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.Label { Layout.fillWidth: true; text: modelData.path; elide: Text.ElideMiddle; font.bold: true }
                            Controls.Label { Layout.fillWidth: true; text: modelData.signature; opacity: 0.75; elide: Text.ElideRight }
                        }
                        Controls.Button {
                            text: "Move to quarantine"
                            icon.name: "security-medium"
                            onClicked: {
                                var r = backend.quarantineFile(modelData.path, modelData.signature)
                                malwareNote = r.message; malwareNoteOk = r.ok
                                refreshMalware()
                            }
                        }
                    }
                }

                // A scan or an install running
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: scanning || malwareBusy
                    Controls.Label {
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                        text: scanning ? (scanFiles > 0 ? "Checked " + scanFiles + " files… " + scanPath : "Loading virus definitions…") : scanPath
                    }
                    RowLayout {
                        ReyOSProgressBar { Layout.fillWidth: true; indeterminate: true }
                        Controls.Button { visible: scanning; text: "Stop"; icon.name: "process-stop"; onClicked: backend.cancelMalwareScan() }
                    }
                }

                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    visible: malwareNote !== ""
                    type: malwareNoteOk ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
                    text: malwareNote
                    showCloseButton: true
                    onVisibleChanged: if (!visible) malwareNote = ""
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.Button {
                        visible: !malware.installed
                        text: "Install scanner"
                        icon.name: "download"
                        highlighted: true
                        enabled: !malwareBusy
                        onClicked: { malwareBusy = true; malwareNote = ""; backend.installMalwareScanner() }
                    }
                    Controls.Button {
                        visible: malware.installed
                        text: "Quick scan"
                        icon.name: "edit-find"
                        highlighted: true
                        enabled: !scanning && !malwareBusy
                        Controls.ToolTip.visible: hovered
                        Controls.ToolTip.text: "Downloads, Desktop and your games: " + (malware.quickScope || []).join(", ")
                        onClicked: startScan("quick")
                    }
                    Controls.Button {
                        visible: malware.installed
                        text: "Choose folder…"
                        icon.name: "folder-open"
                        enabled: !scanning && !malwareBusy
                        Controls.ToolTip.visible: hovered
                        Controls.ToolTip.text: "Any folder, an external drive or SD card too"
                        onClicked: backend.browsePath("malwareFolder", true)
                    }
                    Controls.Button {
                        visible: malware.installed
                        text: "Full home scan"
                        icon.name: "user-home"
                        enabled: !scanning && !malwareBusy
                        Controls.ToolTip.visible: hovered
                        Controls.ToolTip.text: "Everything in your home folder. Can take a long time."
                        onClicked: startScan("home")
                    }
                    Controls.Button {
                        visible: malware.installed
                        text: "Update definitions"
                        icon.name: "view-refresh"
                        enabled: !scanning && !malwareBusy
                        onClicked: { malwareBusy = true; malwareNote = ""; backend.updateMalwareDefinitions() }
                    }
                    Controls.Button {
                        visible: malware.quarantineCount > 0
                        text: "Quarantine (" + malware.quarantineCount + ")…"
                        icon.name: "security-medium"
                        onClicked: quarantineDialog.open()
                    }
                }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.65
                    visible: malware.installed
                    text: "A scan finds known threats only: \"No known threats found\" isn't a guarantee. Keep ReyOS updated and get games and programs from places you trust."
                }
            }
        }

        // Files moved out of the way by a scan: restore or delete, one by one.
        Kirigami.Dialog {
            id: quarantineDialog
            title: "Quarantine"
            preferredWidth: Kirigami.Units.gridUnit * 34
            standardButtons: Kirigami.Dialog.Close
            property var items: []
            property var pending: ({})
            property string pendingAction: ""
            onOpened: items = backend.quarantineItems()
            ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    opacity: 0.75
                    text: quarantineDialog.items.length === 0 ? "Nothing in quarantine."
                          : "These files can't run from here. Restore one only if you're sure it was a false alarm."
                }
                Repeater {
                    model: quarantineDialog.items
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.Label { Layout.fillWidth: true; text: modelData.original_path; elide: Text.ElideMiddle; font.bold: true }
                            Controls.Label {
                                Layout.fillWidth: true; opacity: 0.75; elide: Text.ElideRight
                                text: modelData.signature + " · " + new Date(modelData.quarantined_at * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat)
                            }
                        }
                        Controls.Button { text: "Restore…"; onClicked: { quarantineDialog.pending = modelData; quarantineDialog.pendingAction = "restore"; confirmDialog.open() } }
                        Controls.Button { text: "Delete…"; icon.name: "edit-delete"; onClicked: { quarantineDialog.pending = modelData; quarantineDialog.pendingAction = "delete"; confirmDialog.open() } }
                    }
                }
            }
        }
        Kirigami.PromptDialog {
            id: confirmDialog
            readonly property var item: quarantineDialog.pending
            readonly property bool restoring: quarantineDialog.pendingAction === "restore"
            title: restoring ? "Restore this file?" : "Delete this file for good?"
            subtitle: (item.original_path || "") + "\n" + (restoring
                      ? "It was found as " + item.signature + ". Restore it only if you're sure it's a false alarm: it goes back where it was."
                      : "It can't be brought back afterwards.")
            standardButtons: Kirigami.Dialog.Cancel
            customFooterActions: [
                Kirigami.Action {
                    text: confirmDialog.restoring ? "Restore" : "Delete"
                    icon.name: confirmDialog.restoring ? "edit-undo" : "edit-delete"
                    onTriggered: {
                        var r = confirmDialog.restoring ? backend.restoreQuarantined(confirmDialog.item.id)
                                                        : backend.deleteQuarantined(confirmDialog.item.id)
                        malwareNote = r.message; malwareNoteOk = r.ok
                        confirmDialog.close()
                        quarantineDialog.items = backend.quarantineItems()
                        refreshMalware()
                    }
                }
            ]
        }

        Controls.Label {
            id: usbGuardStatusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        // The page's Refresh action renders as a fixed bottom toolbar
        // (Kirigami's contextual-actions bar) that sits on top of the
        // scrollable content rather than reserving its own space -- without
        // this, the last row of cards ends up partly hidden behind it.
        Item { Layout.fillWidth: true; Layout.preferredHeight: Kirigami.Units.gridUnit * 3 }
    }
}
