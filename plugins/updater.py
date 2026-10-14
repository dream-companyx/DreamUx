"""DreamUX Updater — обновление ядра, плагинов и GUI.
ВАЖНО: НЕ перезаписывает файлы, которые ты меняешь локально.
Файлы, помеченные 'local', исключены из обновления.
"""

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


# ------------------------------------------------------------
# Файлы, которые НЕ перезаписываем (твои локальные правки)
# ------------------------------------------------------------
_LOCAL_FILES = {
    "kernel.py",
    "plugins/vfs.py",
    "plugins/drxfs.py",
    "plugins/gui_server.py",
    "plugins/gnome.py",
    "plugins/gnome_consol.py",
    "plugins/dupfi.py",
    "gnome_gui.py",
    "lock_screen.py",
}


CORE_FILES = {
    "version.json":             f"{CORE_BASE}/version.json",
    "plugins/__init__.py":      f"{CORE_BASE}/plugins/__init__.py",
    "plugins/base.py":          f"{CORE_BASE}/plugins/base.py",
    "plugins/core.py":          f"{CORE_BASE}/plugins/core.py",
    "plugins/filesystem.py":    f"{CORE_BASE}/plugins/filesystem.py",
    "plugins/ui.py":            f"{CORE_BASE}/plugins/ui.py",
    "plugins/access.py":        f"{CORE_BASE}/plugins/access.py",
    "plugins/netd.py":          f"{CORE_BASE}/plugins/netd.py",
    "plugins/ovpn.py":          f"{CORE_BASE}/plugins/ovpn.py",
    "plugins/av_bridge.py":     f"{CORE_BASE}/plugins/av_bridge.py",
    "plugins/antivirus.py":     f"{CORE_BASE}/plugins/antivirus.py",
    "plugins/duap.py":          f"{CORE_BASE}/plugins/duap.py",
    "plugins/testgnome.py":     f"{CORE_BASE}/plugins/testgnome.py",
    "plugins/remote_tools.py":  f"{CORE_BASE}/plugins/remote_tools.py",
    "plugins/updater.py":       f"{CORE_BASE}/plugins/updater.py",
}


GUI_FILES = {
    "splash.py":                f"{GUI_BASE}/splash.py",
    "browser_engine.py":        f"{GUI_BASE}/browser_engine.py",
    "games.py":                 f"{GUI_BASE}/games.py",
    "installers.py":            f"{GUI_BASE}/installers.py",
    "remote_tools_gui.py":      f"{GUI_BASE}/remote_tools_gui.py",
    "assets/dreamux.png":       f"{GUI_BASE}/assets/dreamux.png",
}


def _download(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DreamUX-Updater/1.1"})
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
            json.dump(data, f, indent=2, ensure_ascii=False)
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


def _backup_file(path):
    """Создаёт .bak, но НЕ перезаписывает существующий."""
    bak = path + ".bak"
    if os.path.isfile(bak):
        return
    if not os.path.isfile(path):
        return
    try:
        with open(path, "rb") as f_src:
            data = f_src.read()
        with open(bak, "wb") as f_dst:
            f_dst.write(data)
    except Exception:
        pass


def _is_local(rel):
    rel = rel.replace("\\", "/")
    for pat in _LOCAL_FILES:
        if rel == pat or rel.endswith("/" + pat):
            return True
    return False


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
        print(f"  Файлов в CORE:   {len(CORE_FILES)}")
        print(f"  Файлов в GUI:    {len(GUI_FILES)}")
        print(f"  Локальных (пропуск): {len(_LOCAL_FILES)}")
        if core_new != core_cur:
            print(f"  >> Доступно обновление ядра: {core_new}")
        else:
            print(f"  >> Ядро актуально")
        print("=" * 30 + "\n")
    return {
        "core": {"current": core_cur, "remote": core_new, "needs": core_new != core_cur},
        "gui": {"current": "?", "remote": gui_new, "needs": True},
    }


def update_component(component, verbose=True):
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
    skipped = 0
    local_skipped = 0

    for rel, url in files.items():
        if _is_local(rel):
            local_skipped += 1
            if verbose:
                print(f"  ⊘ {rel}: локальный, не трогаем")
            continue
        dst = os.path.join(base_dir, rel)
        data = _download(url, timeout=30)
        if data is None:
            if verbose:
                print(f"  ✗ {rel}: не скачалось")
            fail += 1
            continue
        head = data[:200].lower()
        if b"<html" in head or b"404: not found" in head:
            if verbose:
                print(f"  ✗ {rel}: 404")
            fail += 1
            continue
        if os.path.isfile(dst):
            try:
                with open(dst, "rb") as f:
                    old = f.read()
                if old == data:
                    skipped += 1
                    if verbose:
                        print(f"  = {rel}: без изменений")
                    continue
            except Exception:
                pass
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            _backup_file(dst)
            with open(dst, "wb") as f:
                f.write(data)
            if verbose:
                print(f"  ✓ {rel} ({len(data)} байт)")
            ok += 1
        except Exception as e:
            if verbose:
                print(f"  ✗ {rel}: {e}")
            fail += 1

    if component == "core":
        remote_ver = _read_remote_version(remote_base) or {}
        local = _read_local_version()
        local["version"] = remote_ver.get("version", local.get("version", "unknown"))
        import datetime as _dt
        local["updated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
        _write_local_version(local)

    print(f"[UPDATER] {component}: обновлено {ok}, "
          f"пропущено {skipped}, локальных {local_skipped}, ошибок {fail}\n")
    return fail == 0


def update_all():
    r1 = update_component("core")
    r2 = update_component("gui")
    if r1 and r2:
        print("[UPDATER] ✅ Всё обновлено")
    else:
        print("[UPDATER] ⚠ Часть не обновилась")


def slash_update(kernel, args):
    cmd = (args[0].lower() if args else "check")
    if cmd == "check":
        update_check(verbose=True)
    elif cmd == "now":
        update_check(verbose=False)
        update_all()
    elif cmd == "core":
        update_component("core")
    elif cmd == "gui":
        update_component("gui")
    elif cmd == "force":
        update_all()
    else:
        print("Updater:")
        print("  /update           — проверить")
        print("  /update now       — проверить и обновить")
        print("  /update core      — только ядро + плагины")
        print("  /update gui       — только GUI")
        print("  /update force     — обновить всё")


def register(kernel):
    kernel.register_slash_command(
        "update", slash_update,
        "Updater — обновление ядра, плагинов, GUI",
    )
    return []
