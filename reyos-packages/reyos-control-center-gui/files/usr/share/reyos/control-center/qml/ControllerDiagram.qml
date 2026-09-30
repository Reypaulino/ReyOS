import QtQuick
import org.kde.kirigami as Kirigami

// A drawn gamepad for the controller setup wizard. The button for
// `activeKey` (a CONTROLLER_STEPS key from emulation.py) is lit and pulses;
// face and shoulder labels follow `brand` (xbox / playstation / nintendo).
// With `overrides` ({key: label}, from emulation.system_controls) the labels
// show what each button does on one console instead, and unused ones dim.
Item {
    id: root
    property string activeKey: ""
    property string brand: "generic"
    property var overrides: null
    readonly property bool mapMode: overrides !== null && overrides !== undefined

    // Opaque blends, so overlapping body parts don't show darker seams.
    readonly property color idle: Kirigami.ColorUtils.linearInterpolation(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, 0.28)
    readonly property color bodyColor: Kirigami.ColorUtils.linearInterpolation(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, 0.10)
    readonly property color lit: Kirigami.Theme.highlightColor

    readonly property var labels: ({
        xbox: { b: "A", a: "B", y: "X", x: "Y", l: "LB", r: "RB", l2: "LT", r2: "RT", select: "⧉", start: "≡", menu_toggle: "" },
        playstation: { b: "✕", a: "○", y: "□", x: "△", l: "L1", r: "R1", l2: "L2", r2: "R2", select: "", start: "", menu_toggle: "PS" },
        nintendo: { b: "B", a: "A", y: "Y", x: "X", l: "L", r: "R", l2: "ZL", r2: "ZR", select: "−", start: "+", menu_toggle: "⌂" },
        generic: { b: "", a: "", y: "", x: "", l: "L", r: "R", l2: "L2", r2: "R2", select: "", start: "", menu_toggle: "" }
    })
    function label(key, maxLen) {
        if (mapMode) {
            var v = overrides[key]
            if (!v) return ""
            return v.length <= (maxLen || 2) ? v : "•"
        }
        var set = labels[brand] || labels.generic
        return set[key] || ""
    }
    function isLit(keys) { return keys.indexOf(activeKey) >= 0 }
    function isUsed(keys) {
        if (!mapMode) return true
        for (var i = 0; i < keys.length; i++)
            if (overrides[keys[i]] !== undefined) return true
        return false
    }

    implicitWidth: 320
    implicitHeight: 200

    // Pulse shared by whichever part is lit.
    property real pulse: 1.0
    SequentialAnimation on pulse {
        loops: Animation.Infinite
        running: root.activeKey.length > 0
        NumberAnimation { from: 1.0; to: 0.45; duration: 550; easing.type: Easing.InOutQuad }
        NumberAnimation { from: 0.45; to: 1.0; duration: 550; easing.type: Easing.InOutQuad }
    }

    component Part: Rectangle {
        property var keys: []
        property string text: ""
        readonly property bool on: root.isLit(keys)
        color: on ? root.lit : root.idle
        opacity: on ? root.pulse : (root.isUsed(keys) ? 1.0 : 0.3)
        antialiasing: true
        Text {
            anchors.centerIn: parent
            width: parent.width - 4
            horizontalAlignment: Text.AlignHCenter
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 6
            text: parent.text
            font.pixelSize: Math.max(8, Math.min(parent.height * 0.55, 15))
            font.bold: true
            color: parent.on ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
        }
    }

    component Stick: Item {
        id: stick
        property string click: ""
        property string axisX: ""
        property string axisY: ""
        property string whole: ""
        property bool captionLeft: false
        width: 38; height: 38
        readonly property bool moving: root.activeKey === axisX || root.activeKey === axisY
        Part {
            anchors.fill: parent
            radius: width / 2
            keys: [stick.click, stick.axisX, stick.axisY, stick.whole]
            border.width: 3
            border.color: Qt.darker(color, 1.3)
        }
        Text {
            visible: stick.moving
            text: root.activeKey === stick.axisX ? "→" : "↓"
            color: root.lit
            font.pixelSize: 22
            font.bold: true
            x: root.activeKey === stick.axisX ? parent.width + 2 : (parent.width - width) / 2
            y: root.activeKey === stick.axisX ? (parent.height - height) / 2 : parent.height - 2
        }
        Text {
            // What the stick does on the chosen console, beside it.
            visible: root.mapMode && !!root.overrides[stick.whole]
            text: visible ? root.overrides[stick.whole] : ""
            color: Kirigami.Theme.textColor
            font.pixelSize: 11
            anchors.verticalCenter: parent.verticalCenter
            x: stick.captionLeft ? -width - 4 : parent.width + 4
        }
        Text {
            visible: root.activeKey === stick.click
            text: "click"
            color: root.lit
            font.pixelSize: 11
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height + 1
        }
    }

    Item {
        id: canvas
        width: 320
        height: 200
        scale: Math.min(root.width / width, root.height / height)
        anchors.centerIn: parent

        // Triggers sit behind the bumpers, which sit behind the body.
        Part { keys: ["l2"]; text: root.label("l2", 8); x: 60; y: 4; width: 54; height: 26; radius: 9 }
        Part { keys: ["r2"]; text: root.label("r2", 8); x: 206; y: 4; width: 54; height: 26; radius: 9 }
        Part { keys: ["l"]; text: root.label("l", 8); x: 50; y: 30; width: 74; height: 16; radius: 8 }
        Part { keys: ["r"]; text: root.label("r", 8); x: 196; y: 30; width: 74; height: 16; radius: 8 }

        Rectangle { color: root.bodyColor; x: 42; y: 92; width: 80; height: 100; radius: 40; rotation: 18; antialiasing: true }
        Rectangle { color: root.bodyColor; x: 198; y: 92; width: 80; height: 100; radius: 40; rotation: -18; antialiasing: true }
        Rectangle { color: root.bodyColor; x: 36; y: 42; width: 248; height: 104; radius: 48; antialiasing: true }

        Stick { click: "l3"; axisX: "l_x"; axisY: "l_y"; whole: "lstick"; captionLeft: true; x: 70; y: 56 }
        Stick { click: "r3"; axisX: "r_x"; axisY: "r_y"; whole: "rstick"; x: 176; y: 100 }

        // D-pad
        Item {
            x: 106; y: 98; width: 42; height: 42
            Rectangle { color: root.idle; x: 14; y: 14; width: 14; height: 14 }
            Part { keys: ["up", "dpad"]; x: 14; y: 0; width: 14; height: 15; radius: 2; text: root.activeKey === "up" ? "▲" : "" }
            Part { keys: ["down", "dpad"]; x: 14; y: 27; width: 14; height: 15; radius: 2; text: root.activeKey === "down" ? "▼" : "" }
            Part { keys: ["left", "dpad"]; x: 0; y: 14; width: 15; height: 14; radius: 2; text: root.activeKey === "left" ? "◀" : "" }
            Part { keys: ["right", "dpad"]; x: 27; y: 14; width: 15; height: 14; radius: 2; text: root.activeKey === "right" ? "▶" : "" }
        }

        // Face buttons
        Item {
            x: 206; y: 50; width: 48; height: 48
            Part { keys: ["x"]; text: root.label("x"); x: 15; y: 0; width: 18; height: 18; radius: 9 }
            Part { keys: ["y"]; text: root.label("y"); x: 0; y: 15; width: 18; height: 18; radius: 9 }
            Part { keys: ["a"]; text: root.label("a"); x: 30; y: 15; width: 18; height: 18; radius: 9 }
            Part { keys: ["b"]; text: root.label("b"); x: 15; y: 30; width: 18; height: 18; radius: 9 }
        }

        Part { keys: ["select"]; text: root.label("select"); x: 125; y: 70; width: 22; height: 18; radius: 9 }
        Part { keys: ["start"]; text: root.label("start"); x: 173; y: 70; width: 22; height: 18; radius: 9 }
        Part { keys: ["menu_toggle"]; text: root.label("menu_toggle"); x: 147; y: 44; width: 26; height: 26; radius: 13 }
    }
}
