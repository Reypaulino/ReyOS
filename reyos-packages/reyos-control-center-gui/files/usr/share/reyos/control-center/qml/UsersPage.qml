import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    title: "Users & Groups"

    property bool busy: false

    actions: [
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: { busy = true; backend.listUsers() }
        }
    ]

    Connections {
        target: backend
        function onUsersListed(list) {
            busy = false
            userModel.clear()
            for (var i = 0; i < list.length; i++) userModel.append(list[i])
        }
        function onActionFinished(ok, message) {
            busy = false
            statusLabel.text = message
            statusLabel.color = ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
            if (ok) { busy = true; backend.listUsers() }
        }
    }

    Component.onCompleted: { busy = true; backend.listUsers() }

    ListModel { id: userModel }

    Controls.Dialog {
        id: addUserDialog
        title: "Add user"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay

        property bool valid: newUsername.text.length > 0
            && /^[a-z_][a-z0-9_-]*$/.test(newUsername.text)
            && newPassword.text.length > 0
            && newPassword.text === newPasswordConfirm.text

        onOpened: {
            newUsername.text = ""; newFullName.text = ""
            newPassword.text = ""; newPasswordConfirm.text = ""
            newIsAdmin.checked = false
        }

        // Custom footer instead of standardButtons: binding a standardButton's
        // `enabled` via standardButton(Ok) turned out unreliable (confirmed
        // live -- the button stayed clickable with an empty form; harmless
        // since onAccepted's own guard still blocked the actual backend call,
        // but no visual feedback and no clean way to keep the dialog open on
        // an invalid submit). Owning the buttons directly sidesteps both.
        footer: Controls.DialogButtonBox {
            Controls.Button {
                text: "Create"
                enabled: addUserDialog.valid
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.AcceptRole
                onClicked: {
                    busy = true
                    backend.addUser(newUsername.text, newFullName.text, newPassword.text, newIsAdmin.checked)
                    addUserDialog.close()
                }
            }
            Controls.Button {
                text: "Cancel"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.RejectRole
                onClicked: addUserDialog.close()
            }
        }

        ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            Kirigami.FormLayout {
                Controls.TextField {
                    id: newUsername
                    Kirigami.FormData.label: "Username:"
                    placeholderText: "e.g. jsmith"
                }
                Controls.TextField {
                    id: newFullName
                    Kirigami.FormData.label: "Full name:"
                    placeholderText: "e.g. Jane Smith"
                }
                Controls.TextField {
                    id: newPassword
                    Kirigami.FormData.label: "Password:"
                    echoMode: TextInput.Password
                }
                Controls.TextField {
                    id: newPasswordConfirm
                    Kirigami.FormData.label: "Confirm password:"
                    echoMode: TextInput.Password
                }
                Controls.CheckBox {
                    id: newIsAdmin
                    Kirigami.FormData.label: "Admin:"
                    text: "Can use sudo (wheel group)"
                }
            }
            Controls.Label {
                visible: newUsername.text.length > 0 && !/^[a-z_][a-z0-9_-]*$/.test(newUsername.text)
                text: "Lowercase letters, digits, - and _ only, must start with a letter or _."
                color: Kirigami.Theme.negativeTextColor
                font.pointSize: 9
            }
            Controls.Label {
                visible: newPasswordConfirm.text.length > 0 && newPassword.text !== newPasswordConfirm.text
                text: "Passwords don't match."
                color: Kirigami.Theme.negativeTextColor
                font.pointSize: 9
            }
        }
    }

    Controls.Dialog {
        id: setPasswordDialog
        title: "Set password"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        property string pendingUsername: ""
        property bool valid: pwField.text.length > 0 && pwField.text === pwConfirmField.text

        onOpened: { pwField.text = ""; pwConfirmField.text = "" }

        footer: Controls.DialogButtonBox {
            Controls.Button {
                text: "Set"
                enabled: setPasswordDialog.valid
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.AcceptRole
                onClicked: {
                    busy = true
                    backend.setUserPassword(setPasswordDialog.pendingUsername, pwField.text)
                    setPasswordDialog.close()
                }
            }
            Controls.Button {
                text: "Cancel"
                Controls.DialogButtonBox.buttonRole: Controls.DialogButtonBox.RejectRole
                onClicked: setPasswordDialog.close()
            }
        }

        ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            Kirigami.FormLayout {
                Controls.TextField {
                    id: pwField
                    Kirigami.FormData.label: "New password:"
                    echoMode: TextInput.Password
                }
                Controls.TextField {
                    id: pwConfirmField
                    Kirigami.FormData.label: "Confirm:"
                    echoMode: TextInput.Password
                }
            }
            Controls.Label {
                visible: pwConfirmField.text.length > 0 && pwField.text !== pwConfirmField.text
                text: "Passwords don't match."
                color: Kirigami.Theme.negativeTextColor
                font.pointSize: 9
            }
        }
    }

    Controls.Dialog {
        id: confirmDeleteUser
        title: "Remove user"
        modal: true
        anchors.centerIn: Controls.Overlay.overlay
        standardButtons: Controls.Dialog.Yes | Controls.Dialog.No
        property string pendingUsername: ""

        onOpened: removeHomeCheck.checked = false
        onAccepted: { busy = true; backend.deleteUser(pendingUsername, removeHomeCheck.checked) }

        ColumnLayout {
            Controls.Label {
                text: "Remove user " + confirmDeleteUser.pendingUsername + "? This can't be undone."
                wrapMode: Text.Wrap
            }
            Controls.CheckBox {
                id: removeHomeCheck
                text: "Also delete their home directory"
            }
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
                spacing: Kirigami.Units.smallSpacing
                Kirigami.Heading { text: "Accounts"; level: 3 }
                Repeater {
                    model: userModel
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: index > 0 ? Kirigami.Units.largeSpacing : 0
                        spacing: Kirigami.Units.smallSpacing

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Label { text: fullName; font.bold: true }
                            Controls.Label { text: "(" + username + ")"; opacity: 0.7 }
                            Controls.Label {
                                visible: isAdmin
                                text: "admin"
                                color: Kirigami.Theme.positiveTextColor
                            }
                            Controls.Label {
                                visible: isSelf
                                text: "· this is you"
                                opacity: 0.6
                            }
                            Item { Layout.fillWidth: true }
                        }
                        RowLayout {
                            spacing: Kirigami.Units.smallSpacing
                            Controls.Button {
                                text: isAdmin ? "Remove admin" : "Make admin"
                                enabled: !busy && !isSelf
                                onClicked: { busy = true; backend.setUserAdmin(username, !isAdmin) }
                            }
                            Controls.Button {
                                text: "Set password"
                                enabled: !busy
                                onClicked: { setPasswordDialog.pendingUsername = username; setPasswordDialog.open() }
                            }
                            Controls.Button {
                                text: "Remove"
                                enabled: !busy && !isSelf
                                onClicked: { confirmDeleteUser.pendingUsername = username; confirmDeleteUser.open() }
                            }
                        }
                    }
                }
                Controls.Label {
                    visible: userModel.count === 0 && !busy
                    text: "No user accounts found."
                    opacity: 0.7
                }
            }
        }

        Controls.Button {
            text: "Add user…"
            enabled: !busy
            onClicked: addUserDialog.open()
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
