(function() {
    if (window.__reyosPasswordManagerInstalled) {
        return;
    }
    window.__reyosPasswordManagerInstalled = true;

    function dispatchFilledEvents(input) {
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function setInputValue(input, value) {
        if (!input || !value) {
            return;
        }
        if (input.value === value) {
            return;
        }
        input.focus();
        input.value = value;
        dispatchFilledEvents(input);
    }

    function isVisibleInput(input) {
        if (!input || input.disabled || input.readOnly) {
            return false;
        }
        if (input.offsetParent === null && getComputedStyle(input).position !== "fixed") {
            return false;
        }
        return true;
    }

    function formControls(form) {
        return Array.prototype.slice.call(form.querySelectorAll("input"));
    }

    function findPasswordInput(form) {
        return formControls(form).find(function(input) {
            return input.type === "password" && isVisibleInput(input);
        }) || null;
    }

    function findUsernameInput(form, passwordInput) {
        var controls = formControls(form).filter(function(input) {
            return isVisibleInput(input);
        });
        var passwordIndex = controls.indexOf(passwordInput);
        for (var i = passwordIndex - 1; i >= 0; --i) {
            var type = (controls[i].type || "text").toLowerCase();
            if (["text", "email", "username", "search", "tel", "url", ""].indexOf(type) !== -1) {
                return controls[i];
            }
        }
        return null;
    }

    function firstCredential(credentials) {
        if (!Array.isArray(credentials) || credentials.length === 0) {
            return null;
        }
        var complete = credentials.find(function(entry) {
            return entry && entry.username && entry.password;
        });
        return complete || null;
    }

    function fillKnownLoginForms(bridge) {
        var origin = window.location.origin;
        if (!origin || origin === "null") {
            return;
        }
        bridge.credentialsFor(origin, function(credentials) {
            var credential = firstCredential(credentials);
            if (!credential) {
                return;
            }
            Array.prototype.forEach.call(document.forms, function(form) {
                var passwordInput = findPasswordInput(form);
                if (!passwordInput || passwordInput.value) {
                    return;
                }
                var usernameInput = findUsernameInput(form, passwordInput);
                if (usernameInput && !usernameInput.value) {
                    setInputValue(usernameInput, credential.username);
                }
                setInputValue(passwordInput, credential.password);
            });
        });
    }

    function submittedCredential(form) {
        var passwordInput = findPasswordInput(form);
        if (!passwordInput || !passwordInput.value) {
            return null;
        }
        var usernameInput = findUsernameInput(form, passwordInput);
        var username = usernameInput ? usernameInput.value.trim() : "";
        if (!username) {
            return null;
        }
        return {
            origin: window.location.origin,
            username: username,
            password: passwordInput.value,
        };
    }

    function attachSubmitReporting(bridge) {
        document.addEventListener(
            "submit",
            function(event) {
                var form = event.target;
                if (!(form instanceof HTMLFormElement) || form.__reyosPasswordSubmitHandled) {
                    return;
                }
                var credential = submittedCredential(form);
                if (!credential || !credential.origin || credential.origin === "null") {
                    return;
                }
                form.__reyosPasswordSubmitHandled = true;
                bridge.reportFormSubmit(credential.origin, credential.username, credential.password);
            },
            true
        );
    }

    function whenReady(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback, { once: true });
        } else {
            callback();
        }
    }

    function initializeBridge() {
        if (typeof qt === "undefined" || !qt.webChannelTransport || typeof QWebChannel === "undefined") {
            return;
        }
        new QWebChannel(qt.webChannelTransport, function(channel) {
            var bridge = channel.objects.passwordBridge;
            if (!bridge) {
                return;
            }
            whenReady(function() {
                fillKnownLoginForms(bridge);
                attachSubmitReporting(bridge);
            });
        });
    }

    initializeBridge();
})();
