// ReyOS System Menu: the logo at the left of the top bar. Clicking it opens a
// native menu (PlasmaExtras.Menu, so it is not clipped to the panel's height).
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.plasma.private.sessions as Sessions
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    preferredRepresentation: fullRepresentation
    Plasmoid.icon: "reyos-launcher"
    Plasmoid.title: "ReyOS"

    Sessions.SessionManagement { id: session }

    Plasma5Support.DataSource {
        id: launcher
        engine: "executable"
        connectedSources: []
        onNewData: (source) => disconnectSource(source)
    }

    function run(command) {
        launcher.connectSource("setsid -f " + command + " >/dev/null 2>&1")
    }

    fullRepresentation: MouseArea {
        id: button

        Layout.minimumWidth: Kirigami.Units.iconSizes.small + Kirigami.Units.largeSpacing
        Layout.preferredWidth: Layout.minimumWidth
        Layout.fillHeight: true
        hoverEnabled: true
        onClicked: menu.openRelative()

        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 6
            color: Kirigami.Theme.highlightColor
            opacity: button.containsMouse || menu.status === PlasmaExtras.Menu.Open ? 0.25 : 0
        }

        Kirigami.Icon {
            anchors.centerIn: parent
            width: Math.min(parent.height - 6, Kirigami.Units.iconSizes.smallMedium)
            height: width
            source: "reyos-launcher"
        }

        PlasmaExtras.Menu {
            id: menu
            visualParent: button

            PlasmaExtras.MenuItem {
                text: i18n("Control Center")
                icon: "reyos-control-center"
                onClicked: root.run("/usr/share/reyos/control-center/main.py")
            }
            PlasmaExtras.MenuItem {
                text: i18n("System Settings")
                icon: "preferences-system"
                onClicked: root.run("systemsettings")
            }
            PlasmaExtras.MenuItem { separator: true }
            PlasmaExtras.MenuItem {
                text: i18n("Lock Screen")
                icon: "system-lock-screen"
                onClicked: session.lock()
            }
            PlasmaExtras.MenuItem {
                text: i18n("Sleep")
                icon: "system-suspend"
                visible: session.canSuspend
                onClicked: session.suspend()
            }
            PlasmaExtras.MenuItem { separator: true }
            PlasmaExtras.MenuItem {
                text: i18n("Restart…")
                icon: "system-reboot"
                onClicked: session.requestReboot()
            }
            PlasmaExtras.MenuItem {
                text: i18n("Shut Down…")
                icon: "system-shutdown"
                onClicked: session.requestShutdown()
            }
            PlasmaExtras.MenuItem {
                text: i18n("Log Out…")
                icon: "system-log-out"
                onClicked: session.requestLogout()
            }
        }
    }
}
