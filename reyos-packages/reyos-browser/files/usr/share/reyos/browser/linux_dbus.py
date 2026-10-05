"""Session-bus helpers built on jeepney (pure Python, no compiled deps).

Used where python-secretstorage (which needs `cryptography`) and notify-send
aren't available -- in practice, the Flatpak build. Exposes the small subset of
secretstorage's API that PasswordVault uses, over a "plain" Secret Service
session: the secret travels unencrypted, but only over the local session bus,
the same channel the D-Bus daemon already trusts.
"""

from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
from jeepney.io.blocking import Proxy, open_dbus_connection
from jeepney.wrappers import DBusErrorResponse, unwrap_msg

SS_BUS = "org.freedesktop.secrets"
SS_PATH = "/org/freedesktop/secrets"
SS_SERVICE = "org.freedesktop.Secret.Service"
SS_COLLECTION = "org.freedesktop.Secret.Collection"
SS_ITEM = "org.freedesktop.Secret.Item"
SS_PROMPT = "org.freedesktop.Secret.Prompt"
PROPS = "org.freedesktop.DBus.Properties"
PROMPT_TIMEOUT = 120

_connection = None


def _bus():
    global _connection
    if _connection is None:
        _connection = open_dbus_connection(bus="SESSION")
    return _connection


def _call(path: str, interface: str, method: str, signature: str = "", body: tuple = ()):
    address = DBusAddress(path, bus_name=SS_BUS, interface=interface)
    return unwrap_msg(_bus().send_and_get_reply(new_method_call(address, method, signature, body)))


def _get_property(path: str, interface: str, name: str):
    return _call(path, PROPS, "Get", "ss", (interface, name))[0][1]


def _run_prompt(prompt_path: str) -> bool:
    """Show a Secret Service prompt (e.g. wallet unlock) and wait for it."""
    if prompt_path == "/":
        return True
    connection = _bus()
    rule = MatchRule(type="signal", interface=SS_PROMPT, member="Completed", path=prompt_path)
    Proxy(message_bus, connection).AddMatch(rule)
    with connection.filter(rule) as queue:
        _call(prompt_path, SS_PROMPT, "Prompt", "s", ("",))
        dismissed, _result = connection.recv_until_filtered(queue, timeout=PROMPT_TIMEOUT).body
    return not dismissed


class Item:
    def __init__(self, session: str, path: str) -> None:
        self._session = session
        self._path = path

    def get_attributes(self) -> dict:
        return dict(_get_property(self._path, SS_ITEM, "Attributes"))

    def get_secret(self) -> bytes:
        return bytes(_call(self._path, SS_ITEM, "GetSecret", "o", (self._session,))[0][2])

    def delete(self) -> None:
        _run_prompt(_call(self._path, SS_ITEM, "Delete")[0])


class Collection:
    def __init__(self, session: str, path: str) -> None:
        self._session = session
        self._path = path

    def is_locked(self) -> bool:
        return bool(_get_property(self._path, SS_COLLECTION, "Locked"))

    def unlock(self) -> None:
        unlocked, prompt = _call(SS_PATH, SS_SERVICE, "Unlock", "ao", ([self._path],))
        if self._path not in unlocked and not _run_prompt(prompt):
            raise RuntimeError("Password wallet unlock was dismissed.")

    def create_item(self, label: str, attributes: dict, secret: bytes, replace: bool = False) -> Item:
        properties = {
            f"{SS_ITEM}.Label": ("s", label),
            f"{SS_ITEM}.Attributes": ("a{ss}", attributes),
        }
        item_path, prompt = _call(
            self._path, SS_COLLECTION, "CreateItem", "a{sv}(oayays)b",
            (properties, (self._session, b"", secret, "text/plain"), replace),
        )
        if item_path == "/":
            _run_prompt(prompt)
            matches = self.search_items(attributes)
            if not matches:
                raise RuntimeError("Password wallet refused to store the item.")
            return matches[0]
        return Item(self._session, item_path)

    def search_items(self, attributes: dict) -> list[Item]:
        paths = _call(self._path, SS_COLLECTION, "SearchItems", "a{ss}", (attributes,))[0]
        return [Item(self._session, path) for path in paths]


def dbus_init():
    try:
        _output, session = _call(SS_PATH, SS_SERVICE, "OpenSession", "sv", ("plain", ("s", "")))
    except (DBusErrorResponse, OSError, KeyError) as error:
        raise RuntimeError(f"No Secret Service provider is available in this session ({error}).") from error
    return session


def check_service_availability(session) -> bool:
    return bool(session)


def get_default_collection(session) -> Collection:
    path = _call(SS_PATH, SS_SERVICE, "ReadAlias", "s", ("default",))[0]
    if path == "/":
        path = f"{SS_PATH}/aliases/default"
    return Collection(session, path)


def notify(app_name: str, icon: str, title: str, message: str) -> None:
    address = DBusAddress(
        "/org/freedesktop/Notifications",
        bus_name="org.freedesktop.Notifications",
        interface="org.freedesktop.Notifications",
    )
    _bus().send(new_method_call(
        address, "Notify", "susssasa{sv}i",
        (app_name, 0, icon, title, message, [], {}, -1),
    ))


__all__ = [
    "DBusErrorResponse",
    "check_service_availability",
    "dbus_init",
    "get_default_collection",
    "notify",
]
