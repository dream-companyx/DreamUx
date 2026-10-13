"""Контроль доступа DreamUX."""

import os
import json
import getpass


LEVEL_SYSTEM = 0
LEVEL_ADMIN  = 1
LEVEL_USER   = 2
LEVEL_GUEST  = 3
LEVEL_APP    = 4

LEVEL_NAMES = {
    0: "СИСТЕМА",
    1: "АДМИНИСТРАТОР",
    2: "ПОЛЬЗОВАТЕЛЬ",
    3: "ГОСТЬ",
    4: "ПРИЛОЖЕНИЕ",
}


PERMISSIONS = {
    "install_package":   [0, 1, 2],
    "remove_package":    [0, 1, 2],
    "install_system":    [0, 1],
    "remove_system":     [0, 1],
    "update_core":       [0, 1],
    "update_gui":        [0, 1],
    "manage_users":      [0, 1],
    "reset_sandbox":     [0, 1],
    "manage_remote":     [0, 1],
    "view_installed":    [0, 1, 2, 3],
    "launch_app":        [0, 1, 2, 3, 4],
    "shutdown":          [0, 1],
    "reboot":            [0, 1],
    "install_dupi":      [0, 1, 2],
    "duap_create":       [0, 1, 2],
    "duap_verify":       [0, 1, 2, 3],
    "duap_extract":      [0, 1, 2],
}


def can(level, permission):
    return level in PERMISSIONS.get(permission, [])


USERS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "users.json",
)


def _load_users():
    if os.path.isfile(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "system": {"level": 0},
        "admin":  {"level": 1},
        getpass.getuser().lower(): {"level": 2},
        "guest":  {"level": 3},
    }


def _save_users(data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ACCESS] Ошибка: {e}")


def get_user_level(username=None):
    if username is None:
        username = getpass.getuser()
    users = _load_users()
    return users.get(username.lower(), {}).get("level", LEVEL_GUEST)


def set_user_level(username, level):
    users = _load_users()
    users[username.lower()] = {"level": level}
    _save_users(users)


def list_users():
    return [(n, u.get("level", 3)) for n, u in sorted(_load_users().items())]


class Session:
    def __init__(self):
        self.username = getpass.getuser()
        self.level = get_user_level(self.username)

    def can(self, permission):
        return can(self.level, permission)

    def level_name(self):
        return LEVEL_NAMES.get(self.level, "?")


_GLOBAL = None


def get_session():
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Session()
    return _GLOBAL


def set_session(s):
    global _GLOBAL
    _GLOBAL = s
