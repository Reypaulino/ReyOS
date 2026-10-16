import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

// The step-by-step controller setup ("press the button shown"), used by
// Control Center's Gaming page and by ReyOS Games' controller window.
// start(pad) runs it on that pad; finished(ok, message) when it ends.
Controls.Dialog {
    id: setupDialog
    signal finished(bool ok, string message)

    // Optional: the system the setup was opened from (a buttonLayout()
    // map). Then each step also says what the button does in that
    // system's games, and the drawing shows that system's buttons.
    property var system: null
    readonly property string systemKey: ["up", "down", "left", "right"].indexOf(stepKey) >= 0 ? "dpad"
                                        : (stepKey === "l_x" || stepKey === "l_y") ? "lstick"
                                        : (stepKey === "r_x" || stepKey === "r_y") ? "rstick" : stepKey
    readonly property string systemName: system ? system.name.replace(" (needs a fast PC)", "") : ""
    readonly property string systemButton: system && system.labels ? (system.labels[systemKey] || "") : ""

    function start(pad, forSystem) {
        system = forSystem && forSystem.labels ? forSystem : null
        padName = pad.name
        prompt = "Getting ready..."
        hint = ""
        stepKey = ""
        stepIndex = 0
        running = true
        open()
        backend.startControllerSetup(pad.path)
    }

    Connections {
        target: backend
        function onControllerSetupStep(index, total, key, brand, title, hint) {
            setupDialog.stepIndex = index
            setupDialog.stepTotal = total
            setupDialog.stepKey = key
            setupDialog.brand = brand
            setupDialog.prompt = title
            setupDialog.hint = hint
        }
        function onControllerSetupDone(ok, message) {
            setupDialog.running = false
            setupDialog.close()
            setupDialog.finished(ok, message)
        }
    }

    property string padName: ""
    property int stepIndex: 0
    property int stepTotal: 1
    property string prompt: ""
    property string hint: ""
    property string stepKey: ""
    property string brand: "generic"
    property bool running: false
    title: "Set up " + padName + (system ? " for " + systemName : "")
    modal: true
    // Centred in the window, not in the (scrolled) page.
    parent: Controls.Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(parent.width - Kirigami.Units.gridUnit * 2, Kirigami.Units.gridUnit * 26)
    closePolicy: Controls.Popup.NoAutoClose
    onRejected: if (running) backend.cancelControllerSetup()
    contentItem: ColumnLayout {
        spacing: Kirigami.Units.largeSpacing
        Controls.Label {
            text: "Step " + (setupDialog.stepIndex + 1) + " of " + setupDialog.stepTotal
            opacity: 0.7
        }
        ControllerDiagram {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Math.min(setupDialog.availableWidth, Kirigami.Units.gridUnit * 18)
            Layout.preferredHeight: Layout.preferredWidth * 200 / 320
            activeKey: setupDialog.stepKey
            brand: setupDialog.brand
            overrides: setupDialog.system ? setupDialog.system.labels : null
        }
        Kirigami.Heading {
            // A fixed width (not fillWidth) so wrapped text reports its real
            // height and the dialog grows to fit instead of spilling under the buttons.
            Layout.preferredWidth: setupDialog.availableWidth
            level: 2
            wrapMode: Text.Wrap
            text: setupDialog.prompt
        }
        Controls.Label {
            Layout.preferredWidth: setupDialog.availableWidth
            wrapMode: Text.Wrap
            visible: setupDialog.hint.length > 0
            text: setupDialog.hint
        }
        Controls.Label {
            Layout.preferredWidth: setupDialog.availableWidth
            wrapMode: Text.Wrap
            opacity: 0.7
            text: "No such button on your controller? Press Skip."
        }
        // Opened from a system's controller window: what this button does there.
        Controls.Label {
            Layout.preferredWidth: setupDialog.availableWidth
            wrapMode: Text.Wrap
            visible: setupDialog.system !== null
            font.bold: setupDialog.systemButton !== ""
            text: !setupDialog.system ? ""
                  : setupDialog.systemButton !== "" ? "In " + setupDialog.systemName + " games this is " + setupDialog.systemButton + "."
                  : setupDialog.systemName + " doesn't use this one. Press it anyway (other systems do) or press Skip."
        }
    }
    footer: Controls.DialogButtonBox {
        Controls.Button {
            text: "Skip"
            icon.name: "go-next-skip"
            Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.ActionRole
            onClicked: backend.skipControllerStep()
        }
        Controls.Button {
            text: "Cancel"
            Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.RejectRole
        }
    }
}
