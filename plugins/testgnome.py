"""
Плагин диагностики GNOME/DreamUX.
Запуск: /testgnome
"""

import os
import sys
import time
import subprocess
import platform

from plugins.base import Interface


# ---------- Пути ----------
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(GNOME_DIR, "screenshots")

GUI_FILE = os.path.join(GNOME_DIR, "gnome_gui.py")
HELPER_FILES = ["browser.py", "games.py", "installers.py"]
CORE_FILES = ["netd.py", "ovpn.py", "av_bridge.py", "antivirus.py"]


# ============================================================
# Проверки
# ============================================================

def check_python():
    print("\n[Python]")
    print(f"  ✅ executable: {sys.executable}")
    print(f"  ✅ version:    {sys.version.split()[0]}")
    print(f"  ✅ platform:   {platform.platform()}")
    if sys.platform == "win32":
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        ok = os.path.isfile(pythonw)
        mark = "✅" if ok else "⚠ "
        print(f"  {mark} pythonw:   {pythonw} "
              f"{'найден' if ok else 'НЕТ'}")


def check_paths():
    print("\n[Пути]")
    print(f"  PLUGIN_DIR:      {PLUGIN_DIR}")
    print(f"  GNOME_DIR:       {GNOME_DIR}")
    print(f"  LOGS_DIR:        {LOGS_DIR}")
    print(f"  SCREENSHOTS_DIR: {SCREENSHOTS_DIR}")
    for name, path in [
        ("plugins/", PLUGIN_DIR),
        ("plugins/gnome/", GNOME_DIR),
        ("logs/", LOGS_DIR),
        ("screenshots/", SCREENSHOTS_DIR),
    ]:
        mark = "✅" if os.path.isdir(path) else "⛔"
        print(f"  {mark} {name:<16} "
              f"{'есть' if os.path.isdir(path) else 'НЕТ'}")
    print("\n  sys.path (первые 8):")
    for p in sys.path[:8]:
        print(f"    • {p}")


def check_files():
    print("\n[Файлы в plugins/gnome/]")
    if os.path.isfile(GUI_FILE):
        size = os.path.getsize(GUI_FILE)
        print(f"  ✅ gnome_gui.py     ({size:,} байт)")
    else:
        print(f"  ⛔ gnome_gui.py     НЕТ")
    for name in HELPER_FILES:
        p = os.path.join(GNOME_DIR, name)
        if os.path.isfile(p):
            size = os.path.getsize(p)
            print(f"  ✅ {name:<16} ({size:,} байт)")
        else:
            print(f"  ⛔ {name:<16} НЕТ")

    print("\n[Файлы в plugins/ — модули ядра]")
    for name in CORE_FILES:
        p = os.path.join(PLUGIN_DIR, name)
        if os.path.isfile(p):
            size = os.path.getsize(p)
            print(f"  ✅ {name:<16} ({size:,} байт)")
        else:
            print(f"  ⛔ {name:<16} НЕТ")


def check_pyqt():
    print("\n[PyQt6]")
    try:
        import PyQt6
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        print(f"  ✅ PyQt6 установлен")
        print(f"     PyQt версия:   {PYQT_VERSION_STR}")
        print(f"     Qt версия:     {QT_VERSION_STR}")
        print(f"     путь:          {PyQt6.__file__}")
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
            print(f"  ✅ QApplication создаётся")
            screen = app.primaryScreen()
            if screen:
                g = screen.availableGeometry()
                print(f"  ✅ Экран: {g.width()}x{g.height()}")
        except Exception as e:
            print(f"  ⛔ QApplication: {e}")
    except ImportError:
        print(f"  ⛔ PyQt6 НЕ установлен")
        print(f"      Установи: pip install PyQt6")


def check_compile():
    print("\n[Синтаксис gnome_gui.py]")
    if not os.path.isfile(GUI_FILE):
        print("  ⛔ Нет gnome_gui.py")
        return
    code = (
        "import py_compile;"
        f"py_compile.compile(r'{GUI_FILE}', doraise=True);"
        "print('COMPILE_OK')"
    )
    try:
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=15,
        )
        out = (r.stdout + r.stderr).strip()
        if "COMPILE_OK" in out:
            print("  ✅ Синтаксис в порядке")
        else:
            print("  ⛔ Ошибка компиляции:")
            for l in out.splitlines()[:10]:
                print(f"     {l}")
    except Exception as e:
        print(f"  ⚠ {e}")


def try_run():
    print("\n[Пробный запуск gnome_gui.py — 5 сек]")
    if not os.path.isfile(GUI_FILE):
        print(f"  ⛔ Нет файла: {GUI_FILE}")
        return
    try:
        import PyQt6  # noqa
    except ImportError:
        print("  ⛔ PyQt6 не установлен — запуск невозможен")
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [GNOME_DIR, PLUGIN_DIR, env.get("PYTHONPATH", "")]
    )
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["SIMPLEOS_NETD"] = "1"
    env["SIMPLEOS_AV_HOST"] = "1"
    env["SIMPLEOS_GNOME_DIR"] = GNOME_DIR
    env["SIMPLEOS_PLUGIN_DIR"] = PLUGIN_DIR
    env["SIMPLEOS_LOGS_DIR"] = LOGS_DIR
    env["SIMPLEOS_SCREENSHOTS_DIR"] = SCREENSHOTS_DIR

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, "gnome_test.log")

    print(f"  Запускаю на 5 секунд...")
    try:
        log_f = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, GUI_FILE],
            cwd=GNOME_DIR,
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        print(f"  ⛔ Не удалось запустить: {e}")
        return

    time.sleep(5)
    if proc.poll() is None:
        print(f"  ✅ Процесс жив через 5 сек — окно, скорее всего, открыто")
        print(f"     PID={proc.pid}")
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        print("  ℹ Тестовый процесс остановлен")
    else:
        print(f"  ⛔ Процесс завершился с кодом {proc.returncode}")

    try:
        log_f.close()
    except Exception:
        pass

    if os.path.isfile(log_path):
        print(f"\n  --- {log_path} ---")
        try:
            with open(log_path, "r", encoding="utf-8",
                      errors="replace") as f:
                for line in f.readlines()[:30]:
                    print(f"     {line.rstrip()}")
        except Exception:
            pass


def check_processes():
    print("\n[Процессы gnome_gui]")
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                ["wmic", "process", "where",
                 "name='python.exe' or name='pythonw.exe'",
                 "get", "ProcessId,CommandLine"],
                capture_output=True, text=True, timeout=15,
            )
            lines = [l.strip() for l in (r.stdout or "").splitlines()
                     if "gnome_gui" in l.lower()]
            if lines:
                print(f"  Найдено: {len(lines)}")
                for l in lines:
                    print(f"    • {l[:120]}")
            else:
                print("  ✅ Активных gnome_gui нет")
        except Exception as e:
            print(f"  ⚠ wmic: {e}")
    else:
        try:
            r = subprocess.run(["ps", "aux"],
                               capture_output=True, text=True)
            lines = [l for l in r.stdout.splitlines()
                     if "gnome_gui" in l]
            if lines:
                for l in lines:
                    print(f"    • {l[:120]}")
            else:
                print("  ✅ Активных gnome_gui нет")
        except Exception as e:
            print(f"  ⚠ ps: {e}")


def show_logs():
    print(f"\n[gnome_stderr.log]")
    log_path = os.path.join(LOGS_DIR, "gnome_stderr.log")
    if not os.path.isfile(log_path):
        print(f"  ⚠ Файл не найден: {log_path}")
        return
    try:
        with open(log_path, "r", encoding="utf-8",
                  errors="replace") as f:
            lines = f.readlines()
        for l in lines[-40:]:
            print(f"  {l.rstrip()}")
    except Exception as e:
        print(f"  ⛔ {e}")


# ============================================================
# Обработчик /testgnome
# ============================================================

def slash_testgnome(kernel, args):
    sub = (args[0].lower() if args else "full")

    print("\n" + "=" * 60)
    print("  DreamUX — Диагностика GNOME")
    print("=" * 60)

    if sub in ("help", "?", "-h", "--help"):
        print("Использование: /testgnome [что проверить]")
        print("  full / (пусто) — всё (по умолчанию)")
        print("  files          — файлы в plugins/gnome/")
        print("  paths          — пути и sys.path")
        print("  pyqt           — PyQt6 и QApplication")
        print("  compile        — синтаксис gnome_gui.py")
        print("  run            — пробный запуск на 5 сек")
        print("  proc           — запущенные gnome_gui")
        print("  logs           — лог gnome_stderr.log")
        print("=" * 60 + "\n")
        return

    if sub in ("full", ""):
        check_python()
        check_paths()
        check_files()
        check_pyqt()
        check_compile()
        check_processes()
        print("\n" + "-" * 60)
        print("Подсказка: /testgnome run — пробный запуск GUI")
        print("-" * 60)
    elif sub == "files":
        check_files()
    elif sub == "paths":
        check_paths()
    elif sub == "pyqt":
        check_pyqt()
    elif sub == "compile":
        check_compile()
    elif sub == "run":
        try_run()
    elif sub in ("proc", "processes"):
        check_processes()
    elif sub == "logs":
        show_logs()
    else:
        print(f"Неизвестный аргумент: {sub}")
        print("Смотри: /testgnome help")

    print()


# ============================================================
# Регистрация
# ============================================================

def register(kernel):
    kernel.register_slash_command(
        "testgnome",
        slash_testgnome,
        "диагностика GNOME (файлы, пути, PyQt6, запуск)",
    )
    return []