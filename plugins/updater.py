"""
DreamUX Updater — обновление ядра, плагинов и GUI.
БЕЗ установки библиотек.

Slash-команды:
    /update             — проверить обновления
    /update now         — обновить всё
    /update core        — только ядро + плагины
    /update gui         — только GUI
    /update force       — принудительно всё
"""

import os
import json
import urllib.request
import urllib.error

from plugins.base import Interface


# ============================================================
# Пути
# ============================================================
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
VERSION_FILE = os.path.join(KERNEL_DIR, "version.json")


CORE_BASE = "https://raw.githubusercontent.com/dream-companyx/DreamUx/main"
GUI_BASE = "https://raw.githubusercontent.com/dream-companyx/dreamux_gui/main"


CORE_FILES = {
    "kernel.py":                f"{CORE_BASE}/kernel.py",
    "version.json":             f"{CORE_BASE}/version.json",
    "plugins/__init__.py":      f"{CORE_BASE}/plugins/__init__.py",
    "plugins/base.py":          f"{CORE_BASE}/plugins/base.py",
    "plugins/access.py":        f"{CORE_BASE}/plugins/access.py",
    "plugins/core.py":          f"{CORE_BASE}/plugins/core.py",
    "plugins/filesystem.py":    f"{CORE_BASE}/plugins/filesystem.py",
    "plugins/ui.py":            f"{CORE_BASE}/plugins/ui.py",
    "plugins/gnome.py":         f"{CORE_BASE}/plugins/gnome.py",
    "plugins/gnome_consol.py":  f"{CORE_BASE}/plugins/gnome_consol.py",
    "plugins/netd.py":          f"{CORE_BASE}/plugins/netd.py",
    "plugins/ovpn.py":          f"{CORE_BASE}/plugins/ovpn.py",
    "plugins/av_bridge.py":     f"{CORE_BASE}/plugins/av_bridge.py",
    "plugins/antivirus.py":     f"{CORE_BASE}/plugins/antivirus.py",
    "plugins/duap.py":          f"{CORE_BASE}/plugins/duap.py",
    "plugins/dupfi.py":         f"{CORE_BASE}/plugins/dupfi.py",
    "plugins/vfs.py":           f"{CORE_BASE}/plugins/vfs.py",
    "plugins/testgnome.py":     f"{CORE_BASE}/plugins/testgnome.py",
    "plugins/remote_tools.py":  f"{CORE_BASE}/plugins/remote_tools.py",
    "plugins/updater.py":       f"{CORE_BASE}/plugins/updater.py",
}

GUI_FILES = {
    "gnome_gui.py":        f"{GUI_BASE}/gnome_gui.py",
    "lock_screen.py":      f"{GUI_BASE}/lock_screen.py",
    "browser_engine.py":   f"{GUI_BASE}/browser_engine.py",
    "games.py":            f"{GUI_BASE}/games.py",
    "installers.py":       f"{GUI_BASE}/installers.py",
    "remote_tools_gui.py": f"{GUI_BASE}/remote_tools_gui.py",
    "splash.py":           f"{GUI_BASE}/splash.py",
    "assets/dreamux.png":  f"{GUI_BASE}/assets/dreamux.png",
}


# ============================================================
# Утилиты
# ============================================================
def _download(url, timeout=15):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "DreamUX-Updater/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def _read_local_version():
    if os.path.isfile(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": "0.0.0"}


def _write_local_version(data):
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _read_remote_version(repo_base):
    raw = _download(f"{repo_base}/version.json")
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


# ============================================================
# Проверка
# ============================================================
def update_check(verbose=True):
    local = _read_local_version()
    remote_core = _read_remote_version(CORE_BASE) or {}
    remote_gui = _read_remote_version(GUI_BASE) or {}

    core_new = remote_core.get("version", "0.0.0")
    gui_new = remote_gui.get("version", "0.0.0")
    core_cur = local.get("version", "0.0.0")

    if verbose:
        print("\n=== DreamUX Update Check ===")
        print(f"  Ядро (локально): {core_cur}")
        print(f"  Ядро (GitHub):   {core_new}")
        print(f"  GUI (GitHub):    {gui_new}")
        if core_new != core_cur:
            print(f"  >> Доступно обновление ядра: {core_new}")
        else:
            print(f"  >> Ядро актуально")
        print("=" * 30 + "\n")

    return {
        "core": {"current": core_cur, "remote": core_new,
                 "needs": core_new != core_cur},
        "gui":  {"current": "?", "remote": gui_new, "needs": True},
    }


# ============================================================
# Обновление компонентов
# ============================================================
def update_component(component):
    if component == "core":
        files = CORE_FILES
        base_dir = KERNEL_DIR
        remote_base = CORE_BASE
    elif component == "gui":
        files = GUI_FILES
        base_dir = GNOME_DIR
        remote_base = GUI_BASE
    else:
        print(f"[UPDATER] Неизвестный компонент: {component}")
        return False

    print(f"\n[UPDATER] Обновление {component}...")

    os.makedirs(base_dir, exist_ok=True)

    ok = 0
    fail = 0

    for rel, url in files.items():
        dst = os.path.join(base_dir, rel)
        data = _download(url, timeout=30)

        if data is None:
            print(f"  X {rel}: не скачалось")
            fail += 1
            continue

        if b"<html" in data[:200].lower() or b"404: not found" in data[:200].lower():
            print(f"  X {rel}: 404")
            fail += 1
            continue

        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)

            # Бэкап старого файла
            if os.path.isfile(dst):
                try:
                    with open(dst + ".bak", "wb") as f_bak:
                        with open(dst, "rb") as f_old:
                            f_bak.write(f_old.read())
                except Exception:
                    pass

            with open(dst, "wb") as f:
                f.write(data)

            print(f"  OK {rel} ({len(data)} байт)")
            ok += 1
        except Exception as e:
            print(f"  X {rel}: {e}")
            fail += 1

    # Обновляем version.json
    if component == "core":
        remote_ver = _read_remote_version(remote_base) or {}
        local = _read_local_version()
        local["version"] = remote_ver.get("version", "unknown")
        _write_local_version(local)

    print(f"[UPDATER] {component}: обновлено {ok}, ошибок {fail}\n")
    return fail == 0


def update_all():
    r1 = update_component("core")
    r2 = update_component("gui")
    if r1 and r2:
        print("[UPDATER] ✅ Всё обновлено (ядро + плагины + GUI)")
    else:
        print("[UPDATER] ⚠ Часть не обновилась — смотри выше")


# ============================================================
# Slash-команда /update
# ============================================================
def slash_update(kernel, args):
    cmd = (args[0].lower() if args else "check")

    if cmd == "check":
        update_check(verbose=True)

    elif cmd == "now":
        print("[UPDATER] Проверка и обновление...")
        update_check(verbose=False)
        update_all()

    elif cmd == "core":
        update_component("core")

    elif cmd == "gui":
        update_component("gui")

    elif cmd == "force":
        print("[UPDATER] Принудительное обновление всего...")
        update_all()

    else:
        print("Updater:")
        print("  /update           — проверить")
        print("  /update now       — проверить и обновить")
        print("  /update core      — только ядро + плагины")
        print("  /update gui       — только GUI")
        print("  /update force     — принудительно всё")


def register(kernel):
    kernel.register_slash_command(
        "update", slash_update,
        "Updater — обновление ядра, плагинов, GUI",
    )
    return []
