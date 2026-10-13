"""Диагностика GNOME. Запуск: /testgnome"""

import os
import sys
import time
import subprocess
import platform

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(GNOME_DIR, "screenshots")
GUI_FILE = os.path.join(GNOME_DIR, "gnome_gui.py")


def check_python():
    print("\n[Python]")
    print(f"  ✅ executable: {sys.executable}")
    print(f"  ✅ version:    {sys.version.split()[0]}")
    print(f"  ✅ platform:   {platform.platform()}")


def check_paths():
    print("\n[Пути]")
    for name, path in [
        ("plugins/", PLUGIN_DIR),
        ("plugins/gnome_gui/", GNOME_DIR),
        ("logs/", LOGS_DIR),
        ("screenshots/", SCREENSHOTS_DIR),
    ]:
        mark = "✅" if os.path.isdir(path) else "⛔"
        print(f"  {mark} {name:<20} {path}")


def check_files():
    print("\n[Файлы в plugins/gnome_gui/]")
    for name in ["gnome_gui.py", "lock_screen.py", "browser_engine.py",
                 "games.py", "installers.py", "splash.py",
                 "remote_tools_gui.py"]:
        p = os.path.join(GNOME_DIR, name)
        if os.path.isfile(p):
            print(f"  ✅ {name:<24} ({os.path.getsize(p):,} байт)")
        else:
            print(f"  ⛔ {name:<24} НЕТ")


def check_pyqt():
    print("\n[PyQt6]")
    try:
        import PyQt6
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        print(f"  ✅ PyQt6 {PYQT_VERSION_STR} / Qt {QT_VERSION_STR}")
    except ImportError:
        print("  ⛔ PyQt6 не установлен")


def try_run():
    print("\n[Пробный запуск — 5 сек]")
    if not os.path.isfile(GUI_FILE):
        print(f"  ⛔ Нет файла: {GUI_FILE}")
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [GNOME_DIR, PLUGIN_DIR, env.get("PYTHONPATH", "")]
    )
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "gnome_test.log")

    try:
        log_f = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, GUI_FILE],
            cwd=GNOME_DIR, env=env,
            stdout=log_f, stderr=subprocess.STDOUT,
        )
    except Exception as e:
        print(f"  ⛔ {e}")
        return

    time.sleep(5)
    if proc.poll() is None:
        print(f"  ✅ GUI жив (PID={proc.pid})")
        proc.terminate()
    else:
        print(f"  ⛔ GUI упал (код {proc.returncode})")
    try:
        log_f.close()
    except Exception:
        pass


def slash_testgnome(kernel, args):
    sub = (args[0].lower() if args else "full")
    print("\n" + "=" * 60)
    print("  DreamUX — Диагностика GNOME")
    print("=" * 60)

    if sub in ("full", ""):
        check_python()
        check_paths()
        check_files()
        check_pyqt()
    elif sub == "pyqt":
        check_pyqt()
    elif sub == "files":
        check_files()
    elif sub == "paths":
        check_paths()
    elif sub == "run":
        try_run()
    else:
        print(f"  Неизвестный аргумент: {sub}")
        print("  Использование: /testgnome [full|files|paths|pyqt|run]")

    print()


def register(kernel):
    kernel.register_slash_command(
        "testgnome",
        slash_testgnome,
        "диагностика GNOME",
    )
    return []
