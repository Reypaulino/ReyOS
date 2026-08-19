import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: appWindow
    title: "ReyOS Control Center"
    width: 900
    height: 620
    minimumWidth: 760
    minimumHeight: 520

    globalDrawer: Kirigami.GlobalDrawer {
        id: drawer
        modal: false
        // Was collapsible: true -- its "Close Sidebar" footer button ate
        // vertical space that 12 nav items can't spare, and nothing else in
        // this app needs the collapsed (icon-only) drawer state.
        collapsible: false
        // Without an explicit width the drawer sized itself just narrow
        // enough that "Control Center" elided to "Control Ce..." once the
        // header icon got an explicit (larger) size -- pin it wide enough
        // for the title to fit comfortably.
        width: Kirigami.Units.gridUnit * 14

        // The default title/titleIcon header renders the icon at its
        // unconstrained natural size with no padding around it -- our
        // logo source rendered oversized and butted right up against the
        // drawer's top edge. Overriding header: with an explicit icon size
        // and anchors-based padding (not Layout.margins, which
        // HeaderFooterLayout's header slot doesn't respect) fixes both.
        header: Item {
            implicitHeight: headerRow.implicitHeight + Kirigami.Units.largeSpacing * 2
            RowLayout {
                id: headerRow
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: "file:///usr/share/reyos/control-center/assets/reyos-brand.png"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                }
                Kirigami.Heading {
                    text: "Control Center"
                    level: 2
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }

        // Grouped + searchable, matching real System Settings' own sidebar
        // (screenshotted live on the dev VM for reference) rather than the
        // flat 12-item list this used to be -- a category header per
        // cluster (Software, Personalization, Network, Storage, System,
        // Accounts) and a search field up top that filters both items and
        // groups live.
        property var navGroups: [
            { group: "", items: [
                { text: "Home", icon: "go-home", page: "SystemInfoPage.qml" }
            ]},
            { group: "Essentials", items: [
                { text: "Updates", icon: "system-software-update", page: "UpdatesPage.qml" },
                { text: "Appearance", icon: "preferences-desktop-theme", page: "AppearancePage.qml" },
                { text: "Backup", icon: "document-save", page: "BackupPage.qml" },
                { text: "Wi-Fi", icon: "network-wireless", page: "WifiPage.qml" },
                { text: "Network", icon: "network-wired", page: "NetworkPage.qml" },
                { text: "Sound", icon: "audio-speakers", page: "SoundPage.qml" },
                { text: "Users", icon: "system-users", page: "UsersPage.qml" }
            ]},
            { group: "Advanced", items: [
                { text: "Flatpak", icon: "package-x-generic", page: "FlatpakPage.qml" },
                { text: "Bluetooth", icon: "preferences-system-bluetooth", page: "BluetoothPage.qml" },
                { text: "Mouse", icon: "input-mouse", page: "MousePage.qml" },
                { text: "Keyboard", icon: "input-keyboard", page: "KeyboardPage.qml" },
                { text: "Performance", icon: "preferences-system-performance", page: "PerformancePage.qml" },
                { text: "Drivers", icon: "video-display", page: "DriversPage.qml" },
                { text: "Firewall", icon: "security-medium", page: "FirewallPage.qml" },
                { text: "Disk", icon: "drive-harddisk", page: "DiskPage.qml" },
                { text: "Date & Time", icon: "preferences-system-time", page: "DateTimePage.qml" },
                { text: "Services", icon: "system-run", page: "ServicesPage.qml" },
                { text: "Startup Apps", icon: "preferences-system-login", page: "StartupPage.qml" },
                { text: "Permissions", icon: "object-locked", page: "PermissionsPage.qml" }
            ]}
        ]
        property string currentPage: "SystemInfoPage.qml"

        // Strips everything but letters/digits before comparing, so "wifi"
        // still matches "Wi-Fi" (a plain substring match doesn't) and "date
        // time" / "datetime" still matches "Date & Time" -- confirmed live
        // that stripping only whitespace/hyphens left "&" in place, silently
        // failing to match on real-world phrasing of that item's name.
        function normalize(s) {
            return s.toLowerCase().replace(/[^a-z0-9]/g, "")
        }
        function itemMatches(item) {
            return searchField.text.length === 0
                || drawer.normalize(item.text).includes(drawer.normalize(searchField.text))
        }
        function groupHasMatch(group) {
            if (searchField.text.length === 0) return true
            for (var i = 0; i < group.items.length; i++) {
                // Must be drawer.itemMatches, not a bare call -- confirmed
                // live (journalctl) that an unqualified call to a sibling
                // function defined on the same Item throws
                // "ReferenceError: ... is not defined" from this nested
                // delegate context, silently breaking the binding (QML
                // swallows the error into the log, not visible in the UI --
                // it just leaves the group header stuck non-visible). Every
                // other call site in this file already used the qualified
                // form; this was the one that didn't.
                if (drawer.itemMatches(group.items[i])) return true
            }
            return false
        }

        // Flattened, pre-filtered list -- replaces the old nested
        // Repeater-in-Repeater-in-ColumnLayout with per-item visible:
        // toggling. That scheme relied on ColumnLayout excluding invisible
        // children from layout to shrink the list down to just the matches;
        // confirmed live (by reordering navGroups and watching the failure
        // follow a group's array *index*, not its content) that it wasn't
        // actually doing that -- non-matching rows kept reserving their
        // original layout space, so anything originally positioned past
        // group index 6 stayed pinned below the drawer's visible height no
        // matter how few results a search actually matched, with no
        // scrollbar to reach it. A ListView bound to a flat array containing
        // only the rows that should currently show sidesteps the ambiguity
        // entirely -- there's no invisible-collapse behavior to depend on,
        // since non-matching rows never become delegates in the first place.
        function flatNavModel() {
            var result = []
            for (var g = 0; g < drawer.navGroups.length; g++) {
                var grp = drawer.navGroups[g]
                if (!drawer.groupHasMatch(grp)) continue
                if (grp.group.length > 0) {
                    result.push({ isHeader: true, text: grp.group, icon: "", page: "" })
                }
                for (var i = 0; i < grp.items.length; i++) {
                    if (drawer.itemMatches(grp.items[i])) {
                        result.push({ isHeader: false, text: grp.items[i].text,
                                       icon: grp.items[i].icon, page: grp.items[i].page })
                    }
                }
            }
            return result
        }

        // GlobalDrawer.actions rows have zero spacing between them and the
        // separator row's own height collapses to ~1px, so any attempt at
        // breathing room between rows (plain separators, spacer actions
        // before/after) either looked cramped or wildly oversized -- there's
        // no clean middle ground through that API. Built the nav list by
        // hand instead via `content:`, which keeps GlobalDrawer itself (a
        // fully custom sidebar replacing GlobalDrawer entirely was tried
        // previously and broke Heading text color app-wide for reasons
        // never root-caused) but gives real control over row spacing.
        content: [
            ColumnLayout {
                Layout.fillWidth: true
                // fillHeight: true so the ListView below always has real
                // vertical space to claim and scroll within -- GlobalDrawer's
                // mainContent vertically centers a fillHeight:true child
                // that has room to spare, but the ListView now always
                // reports the full remaining drawer height as its own size
                // regardless of how many rows are currently in its model,
                // so there's never leftover space left for mainContent to
                // center into.
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.leftMargin: Kirigami.Units.smallSpacing
                Layout.rightMargin: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing

                Kirigami.SearchField {
                    id: searchField
                    Layout.fillWidth: true
                    Layout.bottomMargin: Kirigami.Units.smallSpacing
                    placeholderText: "Search…"
                }

                // GlobalDrawer's content area doesn't scroll on its own --
                // with 10 groups/18 items the unfiltered list is taller than
                // the drawer itself, so this needs to be a real Flickable
                // (ListView already is one) rather than a plain ColumnLayout,
                // or anything past the visible height is simply unreachable.
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 0
                    model: drawer.flatNavModel()

                    delegate: Item {
                        width: ListView.view.width
                        height: modelData.isHeader ? Kirigami.Units.gridUnit * 1.8 : Kirigami.Units.gridUnit * 2.1

                        Controls.Label {
                            visible: modelData.isHeader
                            text: modelData.text
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.leftMargin: Kirigami.Units.smallSpacing
                            anchors.bottomMargin: Kirigami.Units.smallSpacing
                            font.bold: true
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            opacity: 0.6
                        }

                        Controls.ItemDelegate {
                            visible: !modelData.isHeader
                            anchors.fill: parent
                            // A previous fix here double-escaped "&" to
                            // "&&" to dodge Controls.ItemDelegate's
                            // mnemonic parsing (which had turned "Date &
                            // Time" into "Date  Time" with a stray
                            // underline) -- confirmed live on a real
                            // install that this control's style does
                            // *not* parse mnemonics after all, so the
                            // escaped form rendered literally as "Date &&
                            // Time" instead. Plain text, no escaping.
                            text: modelData.isHeader ? "" : modelData.text
                            icon.name: modelData.isHeader ? "" : modelData.icon
                            highlighted: !modelData.isHeader && drawer.currentPage === modelData.page
                            onClicked: {
                                if (modelData.isHeader) return
                                drawer.currentPage = modelData.page
                                pageStack.replace(Qt.resolvedUrl(modelData.page))
                            }
                        }
                    }
                }
            }
        ]
    }

    function openReyosPage(page) { drawer.currentPage = page; pageStack.replace(Qt.resolvedUrl(page)) }

    Connections { target: backend; function onPageRequested(page) { appWindow.openReyosPage(page) } }

    pageStack.initialPage: Qt.resolvedUrl(initialPage)
    // Titles bar (not None like Welcome's wizard) -- this is a persistent
    // multi-page app, each page needs its own header/back-context, unlike
    // Welcome's single linear flow.
    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.Titles
    pageStack.columnView.columnResizeMode: Kirigami.ColumnView.SingleColumn
}
