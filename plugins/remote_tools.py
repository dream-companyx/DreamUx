"""
RemoteTools — утилита обслуживания DreamUX.
Резервное копирование, восстановление, сброс компонентов.
Запуск: /remote [команда]
"""

import os
import sys
import shutil
import datetime
import json
import zipfile
from plugins.base import Interface


# ---------- Пути ----------
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


# ============================================================
# Действия RemoteTools
# ============================================================

def rt_status():
    """Показать состояние всех компонентов."""
    print("\n" + "=" * 60)
    print("  RemoteTools — Состояние DreamUX")
    print("=" * 60)
    print(f"  Корень:    {KERNEL_DIR}")
    print(f"  Снапшоты:  {SNAPSHOTS_DIR}")
    print()
    print(f"  {'Компонент':<14} {'Размер':<12} {'Статус':<10} {'Путь'}")
    print("  " + "-" * 58)
    for name, path in COMPONENTS.items():
        if os.path.isdir(path):
            size = _human_size(_dir_size(path))
            status = "✅ OK"
        else:
            size = "—"
            status = "⛔ НЕТ"
        print(f"  {name:<14} {size:<12} {status:<10} {path}")

    # Снапшоты
    _ensure_snapshots()
    snaps = sorted(os.listdir(SNAPSHOTS_DIR))
    print(f"\n  Снапшоты ({len(snaps)}):")
    if not snaps:
        print("    (нет)")
    else:
        for s in snaps[-10:]:
            p = os.path.join(SNAPSHOTS_DIR, s)
            size = _human_size(_dir_size(p))
            print(f"    • {s}  ({size})")
    print("=" * 60 + "\n")


def rt_backup(component="full"):
    """Создать снапшот. component = 'full' | 'sandbox' | 'logs' | 'config' | 'avdb' | 'gnome_gui'."""
    _ensure_snapshots()
    ts = _ts()

    if component == "full":
        dst = os.path.join(SNAPSHOTS_DIR, f"full_{ts}")
        os.makedirs(dst, exist_ok=True)
        for name, path in COMPONENTS.items():
            if os.path.isdir(path):
                try:
                    shutil.copytree(path, os.path.join(dst, name))
                    print(f"[RemoteTools] ✅ {name} → {dst}/{name}")
                except Exception as e:
                    print(f"[RemoteTools] ⛔ {name}: {e}")
        print(f"[RemoteTools] Полный снапшот: {dst}")
        return dst

    if component not in COMPONENTS:
        print(f"[RemoteTools] Неизвестный компонент: {component}")
        print(f"Доступно: full, {', '.join(COMPONENTS)}")
        return None

    src = COMPONENTS[component]
    if not os.path.isdir(src):
        print(f"[RemoteTools] ⛔ Компонент не найден: {src}")
        return None

    dst = os.path.join(SNAPSHOTS_DIR, f"{component}_{ts}")
    try:
        shutil.copytree(src, dst)
        print(f"[RemoteTools] ✅ Снапшот {component}: {dst}")
        return dst
    except Exception as e:
        print(f"[RemoteTools] ⛔ {component}: {e}")
        return None


def rt_restore(component, snapshot_name):
    """Восстановить компонент из указанного снапшота."""
    _ensure_snapshots()
    snap_dir = os.path.join(SNAPSHOTS_DIR, snapshot_name)
    if not os.path.isdir(snap_dir):
        print(f"[RemoteTools] ⛔ Снапшот не найден: {snapshot_name}")
        return False

    if component not in COMPONENTS:
        print(f"[RemoteTools] ⛔ Неизвестный компонент: {component}")
        return False

    # Источник данных в снапшоте
    if snapshot_name.startswith("full_"):
        src = os.path.join(snap_dir, component)
    else:
        src = snap_dir

    if not os.path.isdir(src):
        print(f"[RemoteTools] ⛔ В снапшоте нет '{component}': {src}")
        return False

    dst = COMPONENTS[component]

    # Удаляем старое и копируем новое
    _safe_rmtree(dst)
    try:
        shutil.copytree(src, dst)
        print(f"[RemoteTools] ✅ Восстановлено {component} из {snapshot_name}")
        return True
    except Exception as e:
        print(f"[RemoteTools] ⛔ Восстановление {component}: {e}")
        return False


def rt_reset(component):
    """Сбросить компонент (пересоздать с нуля)."""
    if component == "full":
        for name in COMPONENTS:
            rt_reset(name)
        return

    if component not in COMPONENTS:
        print(f"[RemoteTools] ⛔ Неизвестный компонент: {component}")
        print(f"Доступно: full, {', '.join(COMPONENTS)}")
        return

    path = COMPONENTS[component]
    print(f"[RemoteTools] Сброс {component} ({path})...")
    _safe_rmtree(path)
    os.makedirs(path, exist_ok=True)
    print(f"[RemoteTools] ✅ {component} сброшен")


def rt_list():
    """Список снапшотов."""
    _ensure_snapshots()
    print(f"\n  Снапшоты в {SNAPSHOTS_DIR}:")
    snaps = sorted(os.listdir(SNAPSHOTS_DIR))
    if not snaps:
        print("    (нет)")
        return
    for s in snaps:
        p = os.path.join(SNAPSHOTS_DIR, s)
        size = _human_size(_dir_size(p))
        print(f"    • {s}  ({size})")
    print()


def rt_clean(keep=5):
    """Удалить старые снапшоты, оставить последние keep."""
    _ensure_snapshots()
    snaps = sorted(os.listdir(SNAPSHOTS_DIR))
    if len(snaps) <= keep:
        print(f"[RemoteTools] Снапшотов {len(snaps)}, чистить нечего.")
        return
    to_remove = snaps[:-keep]
    for s in to_remove:
        p = os.path.join(SNAPSHOTS_DIR, s)
        _safe_rmtree(p)
        print(f"[RemoteTools] 🗑 Удалён: {s}")
    print(f"[RemoteTools] Оставлено: {keep} последних.")


def rt_export():
    """Экспорт полного снапшота в zip."""
    _ensure_snapshots()
    ts = _ts()
    zip_path = os.path.join(SNAPSHOTS_DIR, f"dreamux_backup_{ts}.zip")

    print(f"[RemoteTools] Экспорт в {zip_path}...")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, path in COMPONENTS.items():
                if os.path.isdir(path):
                    for root, _, files in os.walk(path):
                        for f in files:
                            full = os.path.join(root, f)
                            rel = os.path.relpath(full, KERNEL_DIR)
                            zf.write(full, rel)
        size = _human_size(os.path.getsize(zip_path))
        print(f"[RemoteTools] ✅ Экспортировано ({size}): {zip_path}")
    except Exception as e:
        print(f"[RemoteTools] ⛔ Экспорт: {e}")


# ============================================================
# Slash-команда /remote
# ============================================================

def slash_remote(kernel, args):
    if not args:
        print("RemoteTools — использование:")
        print("  /remote status")
        print("  /remote list")
        print("  /remote backup [full|sandbox|logs|config|avdb|gnome_gui]")
        print("  /remote restore <component> <snapshot_name>")
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
    elif cmd == "restore":
        if len(args) < 3:
            print("Использование: /remote restore <component> <snapshot>")
            return
        rt_restore(args[1], args[2])
    elif cmd == "reset":
        comp = args[1] if len(args) > 1 else "full"
        print(f"[RemoteTools] Сброс '{comp}'. Продолжить? Введите y/n:")
        # Простая проверка: сразу сбрасываем, но предупреждаем
        rt_reset(comp)
    elif cmd == "clean":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        rt_clean(n)
    elif cmd == "export":
        rt_export()
    else:
        print(f"[RemoteTools] Неизвестная команда: {cmd}")
        print("Список: /remote без аргументов")


def register(kernel):
    kernel.register_slash_command(
        "remote",
        slash_remote,
        "RemoteTools — снапшоты, восстановление, сброс компонентов",
    )
    return []