import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Appearance"

    property bool busy: false
    property string activeThemeId: ""
    property string pendingThemeId: ""

    Component.onCompleted: {
        activeThemeId = backend.activeLookAndFeel()
        lookAndFeelBox.currentIndex = activeThemeId === "org.reyos.light.desktop" ? 1 : 0
    }

    readonly property var lookAndFeelModel: [
        { label: "ReyOS Dark (default)", id: "org.reyos.desktop" },
        { label: "ReyOS Light", id: "org.reyos.light.desktop" },
    ]

    Connections {
        target: backend
        function onActionFinished(ok, message) {
            busy = false
            if (ok && pendingThemeId.length > 0) {
                activeThemeId = pendingThemeId
                pendingThemeId = ""
            }
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
        }
        function onImageSelected(path) {
            busy = false
            if (path.length > 0) wallpaperField.text = path
        }
    }

    ColumnLayout {
        x: Kirigami.Units.gridUnit
        y: Kirigami.Units.gridUnit
        width: parent.width - Kirigami.Units.gridUnit * 2
        spacing: Kirigami.Units.gridUnit

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Look and feel"; level: 3 }
                Controls.Label {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Changes the color scheme, window decoration, and icon theme together."
                }
                Controls.Label {
                    Layout.fillWidth: true
                    color: Kirigami.Theme.positiveTextColor
                    text: activeThemeId === "org.reyos.light.desktop" ? "Active: ReyOS Light — light surfaces with copper accents." : "Active: ReyOS Dark — Midnight Copper."
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.ComboBox {
                        id: lookAndFeelBox
                        Layout.preferredWidth: 260
                        model: lookAndFeelModel
                        textRole: "label"
                    }
                    Controls.Button {
                        text: "Apply"
                        highlighted: true
                        enabled: !busy
                        onClicked: {
                            pendingThemeId = lookAndFeelModel[lookAndFeelBox.currentIndex].id
                            busy = true
                            backend.applyLookAndFeel(lookAndFeelModel[lookAndFeelBox.currentIndex].id)
                        }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Wallpaper"; level: 3 }
                Controls.Button {
                    text: "Reset to ReyOS default"
                    enabled: !busy
                    onClicked: { busy = true; backend.resetWallpaper() }
                }
                RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Controls.TextField {
                        id: wallpaperField
                        Layout.fillWidth: true
                        placeholderText: "~/Pictures/some-image.jpg"
                    }
                    Controls.Button {
                        text: "Browse…"
                        enabled: !busy
                        onClicked: { busy = true; backend.pickWallpaperImage() }
                    }
                }
                Controls.Button {
                    text: "Set as wallpaper"
                    enabled: !busy && wallpaperField.text.length > 0
                    onClicked: { busy = true; backend.applyWallpaper(wallpaperField.text) }
                }
            }
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }

        Controls.ProgressBar {
            Layout.fillWidth: true
            indeterminate: busy
            visible: busy
        }
    }
}
