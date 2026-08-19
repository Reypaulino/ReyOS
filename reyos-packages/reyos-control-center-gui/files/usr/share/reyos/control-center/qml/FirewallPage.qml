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
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) refresh()
        }
    }

    Component.onCompleted: refresh()

    ListModel { id: ruleModel }

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
                    text: defaultPolicy
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
                    text: "No rules yet."
                    opacity: 0.7
                }
            }
        }

        Controls.ProgressBar {
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
