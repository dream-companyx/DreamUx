#!/usr/bin/env python3
"""
DreamUX Boot — загрузчик.
    VHD есть → ядро → GUI → LockScreen → Рабочий стол
    VHD нет  → мастер → ядро → GUI → LockScreen → Рабочий стол
"""

import os
import sys
import json
import time
import subprocess


_HERE = os.path.dirname(os.path.abspath(__file__))
VFS_CONFIG = os.path.join(_HERE, "vfs", "disks.json")
KERNEL = os.path.join(_HERE, "kernel.py")
USERS_FILE = os.path.join(_HERE, "users.json")


def _is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def is_vfs_ready():
    if not os.path.isfile(VFS_CONFIG):
        return False
    if not os.path.isfile(USERS_FILE):
        return False
    try:
        with open(VFS_CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for key, info in cfg.get("disks", {}).items():
            path = info.get("file", "")
            if path and not os.path.isfile(path):
                return False
        return True
    except Exception:
        return False


def find_pythonw():
    exe = sys.executable
    if os.name == "nt":
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(pyw):
            return pyw
    return exe


def run_setup_wizard():
    print("[BOOT] VFS не найдена — запускаю мастер настройки")
    setup = os.path.join(_HERE, "setup_wizard.py")
    if not os.path.isfile(setup):
        print(f"[BOOT] ⛔ Не найден: {setup}")
        return False
    if not _is_admin():
        print("[BOOT] ⛔ Нужны права администратора")
        return False
    pythonw = find_pythonw()
    try:
        proc = subprocess.Popen([pythonw, setup], cwd=_HERE)
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        print(f"[BOOT] ⛔ Ошибка мастера: {e}")
        return False


def run_kernel():
    print("[BOOT] Запуск ядра DreamUX")
    if not os.path.isfile(KERNEL):
        print(f"[BOOT] ⛔ Не найден: {KERNEL}")
        return False
    pythonw = find_pythonw()
    env = os.environ.copy()
    env["DREAMUX_BOOT"] = "1"
    env["DREAMUX_SHOW_LOCKSCREEN"] = "1"
    try:
        proc = subprocess.Popen([pythonw, KERNEL], cwd=_HERE, env=env)
        proc.wait()
        return proc.returncode == 0
    except Exception as e:
        print(f"[BOOT] ⛔ Ошибка ядра: {e}")
        return False


def main():
    print("=" * 60)
    print("  DreamUX Boot")
    print("=" * 60)

    if is_vfs_ready():
        print("[BOOT] ✅ VFS найдена → запуск ядра")
        print("[BOOT]    Пользователь увидит LockScreen")
        run_kernel()
        return 0

    print("[BOOT] ⚠ VFS не найдена → мастер настройки")
    ok = run_setup_wizard()
    if not ok:
        print("[BOOT] ⛔ Мастер завершился с ошибкой")
        return 1
    if not is_vfs_ready():
        print("[BOOT] ⛔ После мастера VFS всё ещё не готова")
        return 1
    print("[BOOT] ✅ Мастер завершён. Запускаю ядро.")
    time.sleep(1)
    run_kernel()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
