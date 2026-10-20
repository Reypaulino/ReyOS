import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Firewall"

    property bool busy: false
    // Named fwEnabled, not "enabled" -- every QML Item/Control already has
    // a built-in `enabled` property, and a same-named page property gets
    // shadowed by it inside any nested Item's own binding (the Button and
    // Label below were silently reading their *own* enabled state instead
    // of this one -- confirmed live: status showed "Active" in green no
    // matter what ufw's real state was, since Label.enabled defaults to
    // true unless set).
    property bool fwEnabled: false
    property string defaultPolicy: ""

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: refresh()
        }
    ]

    function refresh() {
        busy = true
        backend.refreshFirewallStatus()
        backend.refreshFirewallListening()
    }

    Connections {
        target: backend
        function onFirewallStatusReady(info) {
            busy = false
            fwEnabled = info.enabled
            defaultPolicy = info.defaultPolicy || ""
            ruleModel.clear()
            for (var i = 0; i < info.rules.length; i++) ruleModel.append(info.rules[i])
        }
        function onFirewallListeningReady(rows) {
            listeningModel.clear()
            for (var i = 0; i < rows.length; i++) listeningModel.append(rows[i])
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = ok ? "" : message  // success is shown by Main.qml's toast
            statusLabel.color = Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: ruleModel }
    ListModel { id: listeningModel }

    // Disabling only weakens your own protection (no local-escalation risk),
    // but it's still easy to click by accident right next to Enable -- same
    // confirm-before-destructive pattern as Services' Stop/Disable.
    Controls.Dialog {
        id: confirmDisable
        title: "Disable firewall"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        onAccepted: { busy = true; backend.setFirewallEnabled(false) }
        Controls.Label {
            text: "Disable the firewall? Every port will be reachable until it's turned back on."
            wrapMode: Text.Wrap
        }
    }

    Controls.Dialog {
        id: confirmRemoveRule
        title: "Remove rule"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingNum: ""
        property string pendingRule: ""
        onAccepted: { busy = true; backend.removeFirewallRule(pendingNum) }
        Controls.Label {
            text: "Remove rule: " + confirmRemoveRule.pendingRule + "?"
            wrapMode: Text.Wrap
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
                RowLayout {
                    Layout.fillWidth: true
                    Kirigami.Heading { text: "Status"; level: 3 }
                    Item { Layout.fillWidth: true }
                    Controls.Label {
                        text: fwEnabled ? "Active" : "Inactive"
                        color: fwEnabled ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.disabledTextColor
                        font.bold: true
                    }
                }
                Controls.Label {
                    visible: defaultPolicy.length > 0
                    // ufw's "deny (incoming), allow (outgoing)..." in plain words.
                    text: !fwEnabled ? "Other computers on the network can reach any program here that listens for connections."
                          : (/deny \(incoming\)|reject \(incoming\)/.test(defaultPolicy)
                             ? "Blocks connections from other computers unless a rule below allows them. Your own apps reach the internet as usual."
                             : defaultPolicy)
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    opacity: 0.7
                }
                Controls.Button {
                    text: fwEnabled ? "Disable firewall" : "Enable firewall"
                    enabled: !busy
                    onClicked: {
                        if (fwEnabled) confirmDisable.open()
                        else { busy = true; backend.setFirewallEnabled(true) }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Listening on this computer"; level: 3 }
                Controls.Label {
                    text: "Programs here that accept connections from other computers, and whether the firewall lets them through."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    opacity: 0.7
                }
                Repeater {
                    model: listeningModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Controls.Label { text: name; font.bold: true; Layout.fillWidth: true; elide: Text.ElideRight }
                            Controls.Label {
                                text: "Port " + port + " · " + protos
                                opacity: 0.6
                                font: Kirigami.Theme.smallFont
                            }
                        }
                        Controls.Label {
                            text: status === "allowed" ? "Allowed"
                                  : status === "open" ? "Open (firewall off)"
                                  : status === "outgoing" ? "Works without a rule"
                                  : "Blocked"
                            color: status === "allowed" ? Kirigami.Theme.positiveTextColor
                                   : status === "open" ? Kirigami.Theme.neutralTextColor
                                   : status === "blocked" ? Kirigami.Theme.negativeTextColor
                                   : Kirigami.Theme.textColor
                            Controls.ToolTip.visible: status === "outgoing" && statusHover.hovered
                            Controls.ToolTip.text: "It connects out first, so replies get through without an allow rule."
                            HoverHandler { id: statusHover }
                        }
                        Controls.Button {
                            text: "Allow"
                            visible: status === "blocked"
                            enabled: !busy
                            onClicked: { busy = true; backend.addFirewallRule(rule, true) }
                        }
                    }
                }
                Controls.Label {
                    visible: listeningModel.count === 0
                    text: "Nothing on this computer is listening for connections from other computers."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    opacity: 0.7
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Heading { text: "Add rule"; level: 3 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Controls.TextField {
                        id: portField
                        Layout.fillWidth: true
                        placeholderText: "Port or service, e.g. 22, 22/tcp, http"
                        enabled: !busy
                    }
                    Controls.Button {
                        text: "Allow"
                        enabled: !busy && portField.text.length > 0
                        onClicked: { busy = true; backend.addFirewallRule(portField.text, true); portField.text = "" }
                    }
                    Controls.Button {
                        text: "Deny"
                        enabled: !busy && portField.text.length > 0
                        onClicked: { busy = true; backend.addFirewallRule(portField.text, false); portField.text = "" }
                    }
                }
            }
        }

        Kirigami.AbstractCard {
            Layout.fillWidth: true
            padding: Kirigami.Units.gridUnit
            contentItem: ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Rules"; level: 3 }
                Repeater {
                    model: ruleModel
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Controls.Label { text: "[" + num + "]"; opacity: 0.6; Layout.preferredWidth: 40 }
                        Controls.Label { text: rule; Layout.fillWidth: true; elide: Text.ElideRight }
                        Controls.Button {
                            text: "Remove"
                            enabled: !busy
                            onClicked: {
                                confirmRemoveRule.pendingNum = num
                                confirmRemoveRule.pendingRule = rule
                                confirmRemoveRule.open()
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: ruleModel.count === 0 && !busy
                    text: fwEnabled ? "No rules yet: everything other computers try to open is blocked." : "No rules yet."
                    opacity: 0.7
                }
            }
        }

        ReyOSProgressBar {
            Layout.fillWidth: true
            indeterminate: true
            visible: busy
        }

        Controls.Label {
            id: statusLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
    }
}
