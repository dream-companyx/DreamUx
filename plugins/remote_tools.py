"""
RemoteTools — снапшоты, восстановление, сброс.
Запуск: /remote [команда]
"""

import os
import shutil
import datetime
import zipfile

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
SNAPSHOTS_DIR = os.path.join(KERNEL_DIR, "snapshots")
SANDBOX_DIR = os.path.join(KERNEL_DIR, "sandbox")
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")
CONFIG_DIR = os.path.join(KERNEL_DIR, "config")
AVDB_DIR = os.path.join(KERNEL_DIR, "avdb")

COMPONENTS = {
    "sandbox":   SANDBOX_DIR,
    "logs":      LOGS_DIR,
    "config":    CONFIG_DIR,
    "avdb":      AVDB_DIR,
    "gnome_gui": GNOME_DIR,
}


def _ensure_snapshots():
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)


def _ts():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _human_size(n):
    for u in ["Б", "КБ", "МБ", "ГБ"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} ТБ"


def _dir_size(path):
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _safe_rmtree(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def rt_status():
    print("\n" + "=" * 60)
    print("  RemoteTools — Состояние DreamUX")
    print("=" * 60)
    for name, path in COMPONENTS.items():
        if os.path.isdir(path):
            size = _human_size(_dir_size(path))
            print(f"  {name:<14} {size:<12} OK")
        else:
            print(f"  {name:<14} {'—':<12} НЕТ")

    _ensure_snapshots()
    snaps = sorted(os.listdir(SNAPSHOTS_DIR))
    print(f"\n  Снапшоты ({len(snaps)}):")
    for s in snaps[-10:]:
        p = os.path.join(SNAPSHOTS_DIR, s)
        print(f"    • {s}  ({_human_size(_dir_size(p))})")
    print()


def rt_backup(component="full"):
    _ensure_snapshots()
    ts = _ts()

    if component == "full":
        dst = os.path.join(SNAPSHOTS_DIR, f"full_{ts}")
        os.makedirs(dst, exist_ok=True)
        for name, path in COMPONENTS.items():
            if os.path.isdir(path):
                try:
                    shutil.copytree(path, os.path.join(dst, name))
                    print(f"[RemoteTools] {name} → OK")
                except Exception as e:
                    print(f"[RemoteTools] {name}: {e}")
        print(f"[RemoteTools] Полный снапшот: {dst}")
        return dst

    if component not in COMPONENTS:
        print(f"[RemoteTools] Неизвестный: {component}")
        return None

    src = COMPONENTS[component]
    if not os.path.isdir(src):
        print(f"[RemoteTools] Не найден: {src}")
        return None

    dst = os.path.join(SNAPSHOTS_DIR, f"{component}_{ts}")
    try:
        shutil.copytree(src, dst)
        print(f"[RemoteTools] Снапшот: {dst}")
        return dst
    except Exception as e:
        print(f"[RemoteTools] {e}")
        return None


def rt_reset(component):
    if component == "full":
        for name in COMPONENTS:
            rt_reset(name)
        return
    if component not in COMPONENTS:
        print(f"[RemoteTools] Неизвестный: {component}")
        return
    path = COMPONENTS[component]
    _safe_rmtree(path)
    os.makedirs(path, exist_ok=True)
    print(f"[RemoteTools] {component} сброшен")


def rt_list():
    _ensure_snapshots()
    for s in sorted(os.listdir(SNAPSHOTS_DIR)):
        p = os.path.join(SNAPSHOTS_DIR, s)
        print(f"  • {s}  ({_human_size(_dir_size(p))})")


def rt_clean(keep=5):
    _ensure_snapshots()
    snaps = sorted(os.listdir(SNAPSHOTS_DIR))
    if len(snaps) <= keep:
        print(f"[RemoteTools] Снапшотов {len(snaps)}, чистить нечего.")
        return
    for s in snaps[:-keep]:
        _safe_rmtree(os.path.join(SNAPSHOTS_DIR, s))
        print(f"[RemoteTools] Удалён: {s}")


def rt_export():
    _ensure_snapshots()
    ts = _ts()
    zip_path = os.path.join(SNAPSHOTS_DIR, f"dreamux_backup_{ts}.zip")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, path in COMPONENTS.items():
                if os.path.isdir(path):
                    for root, _, files in os.walk(path):
                        for f in files:
                            full = os.path.join(root, f)
                            rel = os.path.relpath(full, KERNEL_DIR)
                            zf.write(full, rel)
        print(f"[RemoteTools] Экспорт: {zip_path}")
    except Exception as e:
        print(f"[RemoteTools] Экспорт: {e}")


def slash_remote(kernel, args):
    if not args:
        print("RemoteTools:")
        print("  /remote status")
        print("  /remote list")
        print("  /remote backup [full|sandbox|logs|config|avdb|gnome_gui]")
        print("  /remote reset <full|component>")
        print("  /remote clean [N]")
        print("  /remote export")
        return

    cmd = args[0].lower()
    if cmd == "status":
        rt_status()
    elif cmd == "list":
        rt_list()
    elif cmd == "backup":
        comp = args[1] if len(args) > 1 else "full"
        rt_backup(comp)
    elif cmd == "reset":
        comp = args[1] if len(args) > 1 else "full"
        rt_reset(comp)
    elif cmd == "clean":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        rt_clean(n)
    elif cmd == "export":
        rt_export()
    else:
        print(f"[RemoteTools] Неизвестная: {cmd}")


def register(kernel):
    kernel.register_slash_command(
        "remote",
        slash_remote,
        "RemoteTools — снапшоты, сброс",
    )
    return []
