"""
Плагин GNOME-интерфейса DreamUX.
Скачивает gnome_gui.py и остальные файлы в plugins/gnome_gui/.
"""

import os
import sys
import subprocess
import urllib.request

from plugins.base import Interface


# ---------- Пути ----------
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
ASSETS_DIR = os.path.join(GNOME_DIR, "assets")
INIT_FILE = os.path.join(GNOME_DIR, "__init__.py")
GUI_FILE = os.path.join(GNOME_DIR, "gnome_gui.py")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(GNOME_DIR, "screenshots")


# ---------- Репозиторий ----------
BASE_URL = "https://raw.githubusercontent.com/dream-companyx/dreamux_gui/main"

FILES = {
    "gnome_gui.py":        f"{BASE_URL}/gnome_gui.py",
    "browser.py":          f"{BASE_URL}/browser.py",
    "browser_engine.py":   f"{BASE_URL}/browser_engine.py",   # ← новая
    "games.py":            f"{BASE_URL}/games.py",
    "installers.py":       f"{BASE_URL}/installers.py",
    "splash.py":           f"{BASE_URL}/splash.py",
    "remote_tools_gui.py": f"{BASE_URL}/remote_tools_gui.py",
}
ASSETS = {
    "assets/dreamux.png": f"{BASE_URL}/assets/dreamux.png",
}


# ---------- Утилиты ----------
def _ensure_dirs():
    os.makedirs(GNOME_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def _download(url, dst, force=False):
    if os.path.isfile(dst) and not force:
        return True
    try:
        print(f"[GNOME] Скачиваю: {os.path.relpath(dst, GNOME_DIR)}")
        req = urllib.request.Request(
            url, headers={"User-Agent": "DreamUX-GNOME/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        head = data[:300].lower()
        if b"<html" in head or b"404: not found" in head:
            print(f"[GNOME] Ошибка {os.path.basename(dst)}: HTML/404")
            return False
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        print(f"[GNOME] OK {os.path.basename(dst)} ({len(data)} байт)")
        return True
    except Exception as e:
        print(f"[GNOME] Ошибка {os.path.basename(dst)}: {e}")
        return False


def _download_all(force=False):
    ok = True
    for name, url in FILES.items():
        dst = os.path.join(GNOME_DIR, name)
        if not _download(url, dst, force=force):
            ok = False
    for rel, url in ASSETS.items():
        dst = os.path.join(GNOME_DIR, rel)
        if not _download(url, dst, force=force):
            ok = False
    return ok


def _update_missing():
    for name, url in FILES.items():
        dst = os.path.join(GNOME_DIR, name)
        if not os.path.isfile(dst):
            _download(url, dst)
    for rel, url in ASSETS.items():
        dst = os.path.join(GNOME_DIR, rel)
        if not os.path.isfile(dst):
            _download(url, dst)


def _copy_helpers_to_subdir():
    for name in ("netd.py", "ovpn.py", "av_bridge.py", "antivirus.py"):
        src = os.path.join(PLUGIN_DIR, name)
        dst = os.path.join(GNOME_DIR, name)
        if os.path.isfile(src) and not os.path.isfile(dst):
            try:
                with open(src, "rb") as f:
                    data = f.read()
                with open(dst, "wb") as f:
                    f.write(data)
                print(f"[GNOME] Скопирован: {name}")
            except Exception as e:
                print(f"[GNOME] Ошибка копирования {name}: {e}")


# ---------- Плагин ----------
class GnomeDesktop(Interface):
    name = "gnom"
    description = "GNOME-интерфейс DreamUX (PyQt6, Adwaita dark)"

    def __init__(self):
        self._gui_proc = None

    def _prepare(self):
        try:
            _ensure_dirs()
        except Exception as e:
            print(f"[GNOME] _ensure_dirs: {e}")
        try:
            _update_missing()
        except Exception as e:
            print(f"[GNOME] _update_missing: {e}")
        try:
            _copy_helpers_to_subdir()
        except Exception as e:
            print(f"[GNOME] _copy_helpers: {e}")

    def _launch_gui(self, kernel):
        try:
            import PyQt6  # noqa
        except ImportError:
            print("[GNOME] PyQt6 не установлен. pip install PyQt6")
            return

        self._prepare()

        if not os.path.isfile(GUI_FILE):
            if not _download_all():
                print("[GNOME] Не удалось скачать gnome_gui.py")
                return

        if self._gui_proc is not None and self._gui_proc.poll() is None:
            print(f"[GNOME] GUI уже запущен (PID={self._gui_proc.pid})")
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
        env["SIMPLEOS_ASSETS_DIR"] = ASSETS_DIR

        log_path = os.path.join(LOGS_DIR, "gnome_stderr.log")
        print(f"[GNOME] Python: {sys.executable}")
        print(f"[GNOME] Запуск: {GUI_FILE}")
        print(f"[GNOME] CWD:    {GNOME_DIR}")
        print(f"[GNOME] Лог:    {log_path}")

        try:
            log_f = open(log_path, "w", encoding="utf-8")
            self._gui_proc = subprocess.Popen(
                [sys.executable, GUI_FILE],
                cwd=GNOME_DIR,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )
            print(f"[GNOME] GUI запущен (PID={self._gui_proc.pid})")
            print("[GNOME] Ядро продолжает работу. Окно откроется отдельно.")
        except Exception as e:
            print(f"[GNOME] Ошибка запуска: {e}")
            self._gui_proc = None

    def render(self, kernel):
        print("\n[GNOME] Подготовка...")
        self._launch_gui(kernel)

    def handle_input(self, kernel, line):
        if line.strip().lower() in ("exit", "/exit", "quit", "/quit"):
            return True
        if self._gui_proc is None or self._gui_proc.poll() is not None:
            print("[GNOME] GUI не запущен, перезапускаю...")
            self._launch_gui(kernel)
        else:
            print(f"[GNOME] GUI уже запущен (PID={self._gui_proc.pid})")
        return False


def register(kernel):
    print("[GNOME-DEBUG] register() стартовал")
    try:
        kernel.register_interface(GnomeDesktop(), aliases=["gnom", "gnome"])
        print("[GNOME-DEBUG] интерфейс зарегистрирован")
    except Exception as e:
        import traceback
        print(f"[GNOME-DEBUG] Ошибка регистрации: {e}")
        traceback.print_exc()

    try:
        _ensure_dirs()
    except Exception as e:
        print(f"[GNOME] _ensure_dirs: {e}")

    try:
        _update_missing()
    except Exception as e:
        print(f"[GNOME] _update_missing: {e}")

    try:
        _copy_helpers_to_subdir()
    except Exception as e:
        print(f"[GNOME] _copy_helpers: {e}")

    return []
