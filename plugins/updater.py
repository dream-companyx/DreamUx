"""
DreamUX Updater — обновление ядра, плагинов и GUI.

Режимы:
    /update           — проверить обновления
    /update now       — обновить (локальные не трогаются)
    /update core      — только ядро + плагины
    /update gui       — только GUI
    /update force     — ПРИНУДИТЕЛЬНО обновить ВСЁ (даже локальные)
    /update list      — список файлов
"""

import os
import json
import datetime
import urllib.request
import urllib.error

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
VERSION_FILE = os.path.join(KERNEL_DIR, "version.json")


CORE_BASE = "https://raw.githubusercontent.com/dream-companyx/DreamUx/main"
GUI_BASE = "https://raw.githubusercontent.com/dream-companyx/dreamux_gui/main"


# ============================================================
# Локальные файлы (не перезаписываются в /update now, но
# ПЕРЕЗАПИСЫВАЮТСЯ в /update force)
# ============================================================
LOCAL_FILES = {
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


# ============================================================
# CORE_FILES — все файлы ядра и плагинов
# ============================================================
CORE_FILES = {
    # Ядро
    "kernel.py":                        f"{CORE_BASE}/kernel.py",
    "version.json":                     f"{CORE_BASE}/version.json",

    # Плагины — база
    "plugins/__init__.py":              f"{CORE_BASE}/plugins/__init__.py",
    "plugins/base.py":                  f"{CORE_BASE}/plugins/base.py",
    "plugins/core.py":                  f"{CORE_BASE}/plugins/core.py",
    "plugins/filesystem.py":            f"{CORE_BASE}/plugins/filesystem.py",
    "plugins/ui.py":                    f"{CORE_BASE}/plugins/ui.py",

    # Доступ
    "plugins/access.py":                f"{CORE_BASE}/plugins/access.py",

    # GNOME
    "plugins/gnome.py":                 f"{CORE_BASE}/plugins/gnome.py",
    "plugins/gnome_consol.py":          f"{CORE_BASE}/plugins/gnome_consol.py",
    "plugins/gui_server.py":            f"{CORE_BASE}/plugins/gui_server.py",

    # Сеть
    "plugins/netd.py":                  f"{CORE_BASE}/plugins/netd.py",
    "plugins/ovpn.py":                  f"{CORE_BASE}/plugins/ovpn.py",
    "plugins/bridge_tap.py":            f"{CORE_BASE}/plugins/bridge_tap.py",

    # Антивирус
    "plugins/av_bridge.py":             f"{CORE_BASE}/plugins/av_bridge.py",
    "plugins/antivirus.py":             f"{CORE_BASE}/plugins/antivirus.py",

    # Пакеты
    "plugins/duap.py":                  f"{CORE_BASE}/plugins/duap.py",
    "plugins/dupfi.py":                 f"{CORE_BASE}/plugins/dupfi.py",
    "plugins/vfs.py":                   f"{CORE_BASE}/plugins/vfs.py",
    "plugins/drxfs.py":                 f"{CORE_BASE}/plugins/drxfs.py",

    # Утилиты
    "plugins/testgnome.py":             f"{CORE_BASE}/plugins/testgnome.py",
    "plugins/remote_tools.py":          f"{CORE_BASE}/plugins/remote_tools.py",
    "plugins/updater.py":               f"{CORE_BASE}/plugins/updater.py",
}


# ============================================================
# GUI_FILES — все файлы GUI
# ============================================================
GUI_FILES = {
    "gnome_gui.py":                     f"{GUI_BASE}/gnome_gui.py",
    "lock_screen.py":                   f"{GUI_BASE}/lock_screen.py",
    "splash.py":                        f"{GUI_BASE}/splash.py",
    "browser_engine.py":                f"{GUI_BASE}/browser_engine.py",
    "games.py":                         f"{GUI_BASE}/games.py",
    "installers.py":                    f"{GUI_BASE}/installers.py",
    "remote_tools_gui.py":              f"{GUI_BASE}/remote_tools_gui.py",
    "assets/dreamux.png":               f"{GUI_BASE}/assets/dreamux.png",
}


# ============================================================
# Утилиты
# ============================================================
def _download(url, timeout=15):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "DreamUX-Updater/1.2"}
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
    """Создаёт .bak. Не перезаписывает существующий .bak."""
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
    for pat in LOCAL_FILES:
        if rel == pat or rel.endswith("/" + pat):
            return True
    return False


# ============================================================
# Проверка обновлений
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
        print(f"  Файлов в CORE:   {len(CORE_FILES)}")
        print(f"  Файлов в GUI:    {len(GUI_FILES)}")
        print(f"  Локальных файлов: {len(LOCAL_FILES)}")
        if core_new != core_cur:
            print(f"  >> Доступно обновление: {core_new}")
        else:
            print(f"  >> Ядро актуально")
        print("=" * 30 + "\n")

    return {
        "core": {"current": core_cur, "remote": core_new,
                 "needs": core_new != core_cur},
        "gui":  {"current": "?", "remote": gui_new, "needs": True},
    }


# ============================================================
# Обновление компонента
# ============================================================
def update_component(component, verbose=True, force=False):
    """
    force=False — локальные файлы НЕ трогаются
    force=True  — ВСЕ файлы перезаписываются
    """
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

    mode = "FORCE (все файлы)" if force else "обычное (локальные пропускаются)"
    print(f"\n[UPDATER] Обновление {component} — {mode}...")

    os.makedirs(base_dir, exist_ok=True)

    ok = 0
    fail = 0
    skipped = 0
    local_skipped = 0

    for rel, url in files.items():
        # Пропускаем локальные, если НЕ force
        if not force and _is_local(rel):
            local_skipped += 1
            if verbose:
                print(f"  ⊘ {rel}: локальный (force для перезаписи)")
            continue

        dst = os.path.join(base_dir, rel)
        data = _download(url, timeout=30)

        if data is None:
            if verbose:
                print(f"  ✗ {rel}: не скачалось")
            fail += 1
            continue

        # Проверка на HTML/404
        head = data[:200].lower()
        if b"<html" in head or b"404: not found" in head:
            if verbose:
                print(f"  ✗ {rel}: 404")
            fail += 1
            continue

        # Пропускаем, если файл идентичен (только если НЕ force)
        if not force and os.path.isfile(dst):
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

            # Бэкап
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

    # Обновляем version.json
    if component == "core":
        remote_ver = _read_remote_version(remote_base) or {}
        local = _read_local_version()
        local["version"] = remote_ver.get(
            "version", local.get("version", "unknown"))
        local["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        _write_local_version(local)

    print(f"[UPDATER] {component}: обновлено {ok}, "
          f"пропущено {skipped}, локальных {local_skipped}, ошибок {fail}\n")
    return fail == 0


# ============================================================
# Обновление всего
# ============================================================
def update_all(force=False):
    r1 = update_component("core", force=force)
    r2 = update_component("gui", force=force)
    if r1 and r2:
        if force:
            print("[UPDATER] ✅ ВСЁ обновлено (принудительно)")
        else:
            print("[UPDATER] ✅ Всё обновлено")
        print("[UPDATER] ⚠ Перезапусти DreamUX для применения")
    else:
        print("[UPDATER] ⚠ Часть не обновилась — смотри выше")


# ============================================================
# Список файлов
# ============================================================
def list_files():
    print("\n=== CORE (ядро + плагины) ===")
    for rel in sorted(CORE_FILES):
        dst = os.path.join(KERNEL_DIR, rel)
        mark = "✅" if os.path.isfile(dst) else "❌"
        local = " [ЛОКАЛЬНЫЙ]" if _is_local(rel) else ""
        print(f"  {mark} {rel}{local}")

    print("\n=== GUI ===")
    for rel in sorted(GUI_FILES):
        dst = os.path.join(GNOME_DIR, rel)
        mark = "✅" if os.path.isfile(dst) else "❌"
        local = " [ЛОКАЛЬНЫЙ]" if _is_local(rel) else ""
        print(f"  {mark} {rel}{local}")
    print()


# ============================================================
# Slash-команда /update
# ============================================================
def slash_update(kernel, args):
    cmd = (args[0].lower() if args else "check")

    if cmd == "check":
        update_check(verbose=True)

    elif cmd == "now":
        print("[UPDATER] Проверка и обновление (локальные не трогаем)...")
        update_check(verbose=False)
        update_all(force=False)

    elif cmd == "core":
        update_component("core", force=False)

    elif cmd == "gui":
        update_component("gui", force=False)

    elif cmd == "force":
        print("[UPDATER] ⚠ ПРИНУДИТЕЛЬНОЕ обновление ВСЕГО")
        print("[UPDATER]   Все локальные файлы будут перезаписаны!")
        print("[UPDATER]   Бэкапы: <файл>.bak")
        print()
        update_all(force=True)

    elif cmd == "force-core":
        print("[UPDATER] ⚠ FORCE: ядро + плагины")
        update_component("core", force=True)

    elif cmd == "force-gui":
        print("[UPDATER] ⚠ FORCE: GUI")
        update_component("gui", force=True)

    elif cmd == "list":
        list_files()

    else:
        print("Updater:")
        print("  /update             — проверить")
        print("  /update now         — обновить (локальные НЕ трогаем)")
        print("  /update core        — только ядро + плагины")
        print("  /update gui         — только GUI")
        print("  /update force       — ПРИНУДИТЕЛЬНО ВСЁ (перезапись)")
        print("  /update force-core  — ПРИНУДИТЕЛЬНО ядро")
        print("  /update force-gui   — ПРИНУДИТЕЛЬНО GUI")
        print("  /update list        — список файлов")


# ============================================================
# Регистрация
# ============================================================
def register(kernel):
    kernel.register_slash_command(
        "update", slash_update,
        "Updater — обновление ядра, плагинов, GUI",
    )
    return []
