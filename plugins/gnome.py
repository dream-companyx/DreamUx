"""Плагин GNOME. Запускает GUI отдельным процессом."""

import os
import sys
import subprocess

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
GUI_FILE = os.path.join(GNOME_DIR, "gnome_gui.py")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(GNOME_DIR, "screenshots")
ASSETS_DIR = os.path.join(GNOME_DIR, "assets")


class GnomeDesktop(Interface):
    name = "gnom"
    description = "GNOME-интерфейс DreamUX (PyQt6, Adwaita dark)"

    def __init__(self):
        self._gui_proc = None
        self.username = None

    def _launch_gui(self, kernel, username=None):
        try:
            import PyQt6  # noqa
        except ImportError:
            print("[GNOME] ⛔ PyQt6 не установлен. pip install PyQt6")
            return

        if not os.path.isfile(GUI_FILE):
            print(f"[GNOME] ⛔ Не найден: {GUI_FILE}")
            return

        for d in (LOGS_DIR, SCREENSHOTS_DIR, ASSETS_DIR):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass

        if self._gui_proc is not None and self._gui_proc.poll() is None:
            print(f"[GNOME] GUI уже запущен (PID={self._gui_proc.pid})")
            return

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [GNOME_DIR, PLUGIN_DIR, os.path.dirname(PLUGIN_DIR),
             env.get("PYTHONPATH", "")]
        )
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["SIMPLEOS_GNOME_DIR"] = GNOME_DIR
        env["SIMPLEOS_PLUGIN_DIR"] = PLUGIN_DIR
        env["SIMPLEOS_LOGS_DIR"] = LOGS_DIR
        env["SIMPLEOS_SCREENSHOTS_DIR"] = SCREENSHOTS_DIR
        env["SIMPLEOS_ASSETS_DIR"] = ASSETS_DIR

        if username:
            env["SIMPLEOS_USERNAME"] = username
            print(f"[GNOME] Пользователь: {username}")

        log_path = os.path.join(LOGS_DIR, "gnome_stderr.log")
        print(f"[GNOME] Python: {sys.executable}")
        print(f"[GNOME] Запуск: {GUI_FILE}")

        try:
            log_f = open(log_path, "w", encoding="utf-8")
            self._gui_proc = subprocess.Popen(
                [sys.executable, GUI_FILE],
                cwd=GNOME_DIR,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )
            print(f"[GNOME] ✅ GUI запущен (PID={self._gui_proc.pid})")
        except Exception as e:
            print(f"[GNOME] ⛔ Ошибка запуска: {e}")
            self._gui_proc = None

    def _stop_gui(self):
        if self._gui_proc is not None and self._gui_proc.poll() is None:
            try:
                self._gui_proc.terminate()
                self._gui_proc.wait(timeout=5)
            except Exception:
                try:
                    self._gui_proc.kill()
                except Exception:
                    pass
            print("[GNOME] GUI остановлен")
        self._gui_proc = None

    def render(self, kernel):
        print("\n" + "=" * 60)
        print("  DreamUX GNOME")
        print("=" * 60)
        if self.username:
            print(f"  Пользователь: {self.username}")
        print("  exit — выход, gnome — перезапуск GUI")
        print("=" * 60 + "\n")
        self._launch_gui(kernel, username=self.username)

    def handle_input(self, kernel, line):
        line = line.strip()
        if not line:
            return False
        if line.lower() in ("exit", "/exit", "quit", "/quit"):
            self._stop_gui()
            return True
        if line.lower() in ("gnome", "gui", "restart"):
            self._stop_gui()
            self._launch_gui(kernel, username=self.username)
            return False
        if line.lower() in ("help", "/help", "?"):
            self.render(kernel)
            return False
        if line.startswith("/"):
            parts = line[1:].split()
            if not parts:
                return False
            token = parts[0].lower()
            args = parts[1:]
            entry = kernel.slash_commands.get(token)
            if entry is None:
                print(f"[GNOME] Неизвестная /команда: /{token}")
                return False
            try:
                entry["handler"](kernel, args)
            except Exception as e:
                import traceback
                print(f"[GNOME] [ошибка /{token}] {e}")
                traceback.print_exc()
            return False
        parts = line.split()
        name, args = parts[0], parts[1:]
        cmd = kernel.commands.get(name)
        if cmd is None:
            print(f"[GNOME] Неизвестная команда: {name}")
            return False
        try:
            cmd.run(kernel, args)
        except Exception as e:
            print(f"[GNOME] [ошибка команды] {e}")
        return False


def slash_gnome(kernel, args):
    iface = GnomeDesktop()
    if args:
        iface.username = args[0]
        print(f"[GNOME] Запуск под пользователем: {iface.username}")
    kernel.run_interface(iface)


def register(kernel):
    print("[GNOME-DEBUG] register() стартовал")
    try:
        kernel.register_interface(GnomeDesktop(), aliases=["gnom", "gnome"])
        kernel.register_slash_command(
            "gnome", slash_gnome, "GNOME — /gnome [username]")
        print("[GNOME-DEBUG] ✅ зарегистрировано")
    except Exception as e:
        import traceback
        print(f"[GNOME-DEBUG] ⛔ {e}")
        traceback.print_exc()
    return []
