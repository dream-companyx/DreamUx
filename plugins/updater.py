"""Автообновление DreamUX. /update [check|now|core|gui|force]"""

import os
import json
import urllib.request

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
VERSION_FILE = os.path.join(KERNEL_DIR, "version.json")


CORE_BASE = "https://raw.githubusercontent.com/dream-companyx/DreamUx/main"
GUI_BASE = "https://raw.githubusercontent.com/dream-companyx/dreamux_gui/main"

CORE_FILES = {
    "kernel.py":                f"{CORE_BASE}/kernel.py",
    "plugins/__init__.py":      f"{CORE_BASE}/plugins/__init__.py",
    "plugins/base.py":          f"{CORE_BASE}/plugins/base.py",
    "plugins/core.py":          f"{CORE_BASE}/plugins/core.py",
    "plugins/filesystem.py":    f"{CORE_BASE}/plugins/filesystem.py",
    "plugins/ui.py":            f"{CORE_BASE}/plugins/ui.py",
    "plugins/gnome.py":         f"{CORE_BASE}/plugins/gnome.py",
    "plugins/netd.py":          f"{CORE_BASE}/plugins/netd.py",
    "plugins/ovpn.py":          f"{CORE_BASE}/plugins/ovpn.py",
    "plugins/av_bridge.py":     f"{CORE_BASE}/plugins/av_bridge.py",
    "plugins/antivirus.py":     f"{CORE_BASE}/plugins/antivirus.py",
    "plugins/testgnome.py":     f"{CORE_BASE}/plugins/testgnome.py",
    "plugins/remote_tools.py":  f"{CORE_BASE}/plugins/remote_tools.py",
    "plugins/updater.py":       f"{CORE_BASE}/plugins/updater.py",
}

GUI_FILES = {
    "gnome_gui.py":        f"{GUI_BASE}/gnome_gui.py",
    "browser.py":          f"{GUI_BASE}/browser.py",
    "browser_engine.py":   f"{GUI_BASE}/browser_engine.py",
    "games.py":            f"{GUI_BASE}/games.py",
    "installers.py":       f"{GUI_BASE}/installers.py",
    "splash.py":           f"{GUI_BASE}/splash.py",
    "remote_tools_gui.py": f"{GUI_BASE}/remote_tools_gui.py",
    "assets/dreamux.png":  f"{GUI_BASE}/assets/dreamux.png",
}


def _download_text(url, timeout=15):
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
    raw = _download_text(f"{repo_base}/version.json")
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


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
        print(f"[Updater] Неизвестный: {component}")
        return False

    print(f"\n[Updater] Обновление {component}...")
    ok = 0
    fail = 0
    for rel, url in files.items():
        dst = os.path.join(base_dir, rel)
        data = _download_text(url)
        if data is None:
            print(f"  X {rel}")
            fail += 1
            continue
        if b"<html" in data[:200].lower() or b"404: not found" in data[:200].lower():
            print(f"  X {rel}: 404")
            fail += 1
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
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

    if component == "core":
        remote_ver = _read_remote_version(remote_base) or {}
        local = _read_local_version()
        local["version"] = remote_ver.get("version", "unknown")
        _write_local_version(local)

    print(f"[Updater] {component}: обновлено {ok}, ошибок {fail}\n")
    return fail == 0


def update_all():
    r1 = update_component("core")
    r2 = update_component("gui")
    if r1 and r2:
        print("[Updater] Всё обновлено.")
    else:
        print("[Updater] Часть не обновилась.")


def slash_update(kernel, args):
    cmd = (args[0].lower() if args else "check")

    if cmd == "check":
        update_check(verbose=True)
    elif cmd == "now":
        print("[Updater] Проверка и обновление...")
        r = update_check(verbose=False)
        if r["core"]["needs"] or r["gui"]["needs"]:
            update_all()
        else:
            print("[Updater] Уже последняя версия.")
    elif cmd == "core":
        update_component("core")
    elif cmd == "gui":
        update_component("gui")
    elif cmd == "force":
        print("[Updater] Принудительное обновление всего...")
        update_all()
    else:
        print("Updater:")
        print("  /update           — проверить")
        print("  /update now       — проверить и обновить")
        print("  /update core      — только ядро")
        print("  /update gui       — только GUI")
        print("  /update force     — принудительно всё")


def register(kernel):
    kernel.register_slash_command(
        "update",
        slash_update,
        "Updater — автообновление",
    )
    return []
