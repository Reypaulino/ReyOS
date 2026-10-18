import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: "Backup Center"

    // Automatic snapshots on btrfs installs (reyos-snapshots).
    property var snapshots: backend.snapshotStatus()

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: page.snapshots.bootedFrom !== ""
            type: Kirigami.MessageType.Warning
            text: "ReyOS is running from the snapshot taken before the update on " + page.snapshots.bootedFrom + ". To keep this version, open Timeshift and restore this snapshot. To go back to your current system, just restart."
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            visible: page.snapshots.on
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Automatic snapshots are on"; level: 2 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Before every system update ReyOS saves a snapshot of your system files and keeps the last " + page.snapshots.keep + ". They take little space, and older ones are removed first when the disk gets full. If an update breaks something, restart and pick \"ReyOS snapshot (before update, …)\" in the boot menu, or restore one in Timeshift."
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Protect your system"; level: 2 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                    text: "Timeshift creates restore points for your system files. Your personal documents are not included, so keep those in a separate backup as well."
                }
                Controls.Button {
                    text: "Open Timeshift"
                    icon.name: "document-save"
                    highlighted: true
                    onClicked: backend.openTimeshift()
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            // Timeshift is already set up when automatic snapshots are on.
            visible: !page.snapshots.on
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Recommended setup"; level: 3 }
                Controls.Label { text: "1. Choose a backup location with enough free space." }
                Controls.Label { text: "2. Create a first restore point before making major changes." }
                Controls.Label { text: "3. Enable a schedule only after confirming a restore point succeeds." }
            }
        }
    }
}
