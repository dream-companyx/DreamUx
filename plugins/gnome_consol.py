"""DreamUX GNOME Consol — консоль + GUI + логи."""

import os
import sys
import time
import threading
import subprocess
import datetime

from plugins.base import Interface


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
GUI_FILE = os.path.join(GNOME_DIR, "gnome_gui.py")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")

LOG_FILES_TO_WATCH = [
    "actions.log", "errors.log", "sandbox.log", "quarantine.log",
    "network.log", "browser.log", "games.log", "installers.log",
    "antivirus.log", "gnome_stderr.log",
]


class GnomeConsol(Interface):
    name = "gnome_consol"
    description = "GNOME Consol — консоль + GUI + логи"

    def __init__(self):
        self._gui_proc = None
        self._log_thread = None
        self._monitor_thread = None
        self._running = False
        self._log_positions = {}
        self.username = None
        self._started_once = False

    def render(self, kernel):
        print("\n" + "=" * 60)
        print("  DreamUX GNOME Consol")
        print("=" * 60)
        if self.username:
            print(f"  Пользователь: {self.username}")
        print("    <команда>           — команда ядра")
        print("    /<команда>          — slash-команда ядра")
        print("    user <имя>          — сменить пользователя")
        print("    logs                — логи GUI")
        print("    clear_logs          — очистить логи")
        print("    exit                — закрыть")
        print("=" * 60)
        print()

    def handle_input(self, kernel, line):
        if not self._running and not self._started_once:
            self._started_once = True
            self._launch_gnome(kernel)
            return False
        line = line.strip()
        if not line:
            return False
        if line in ("exit", "/exit", "quit"):
            self._stop_gnome()
            return True
        if line == "logs":
            self._show_logs()
            return False
        if line == "clear_logs":
            self._clear_logs()
            return False
        if line.lower().startswith("user "):
            new_user = line.split(maxsplit=1)[1].strip()
            self.username = new_user
            print(f"[consol] Смена пользователя: {new_user}")
            self._stop_gnome()
            self._started_once = False
            self._launch_gnome(kernel)
            self._started_once = True
            return False
        if line.startswith("/"):
            parts = line[1:].split()
            if not parts:
                return False
            token = parts[0].lower()
            args = parts[1:]
            if token in ("exit", "halt"):
                self._stop_gnome()
                return True
            if token == "help":
                self._print_help(kernel)
                return False
            if token == "logs":
                self._show_logs()
                return False
            if token == "gnome":
                self._send_to_gui(" ".join(args))
                return False
            entry = kernel.slash_commands.get(token)
            if entry:
                try:
                    entry["handler"](kernel, args)
                except Exception as e:
                    print(f"[ошибка /{token}] {e}")
                return False
            print(f"Неизвестная /команда: /{token}")
            return False
        parts = line.split()
        name, args = parts[0], parts[1:]
        cmd = kernel.commands.get(name)
        if cmd:
            try:
                cmd.run(kernel, args)
            except Exception as e:
                print(f"[ошибка команды] {e}")
        else:
            print(f"Неизвестная команда: {name}")
        return False

    def _launch_gnome(self, kernel):
        print("[consol] Запуск GNOME...")
        try:
            import PyQt6  # noqa
        except ImportError:
            print("[consol] ⛔ PyQt6 не установлен")
            self._running = False
            return
        if not os.path.isfile(GUI_FILE):
            print(f"[consol] ⛔ Не найден {GUI_FILE}")
            self._running = False
            return
        os.makedirs(LOGS_DIR, exist_ok=True)
        stderr_path = os.path.join(LOGS_DIR, "gnome_stderr.log")
        try:
            with open(stderr_path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [GNOME_DIR, PLUGIN_DIR, KERNEL_DIR, env.get("PYTHONPATH", "")]
        )
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["SIMPLEOS_GNOME_DIR"] = GNOME_DIR
        env["SIMPLEOS_PLUGIN_DIR"] = PLUGIN_DIR
        env["SIMPLEOS_LOGS_DIR"] = LOGS_DIR
        if self.username:
            env["SIMPLEOS_USERNAME"] = self.username
            print(f"[consol] Пользователь: {self.username}")
        try:
            log_f = open(stderr_path, "a", encoding="utf-8")
            self._gui_proc = subprocess.Popen(
                [sys.executable, GUI_FILE],
                cwd=GNOME_DIR, env=env,
                stdout=log_f, stderr=subprocess.STDOUT,
            )
            log_f.close()
        except Exception as e:
            print(f"[consol] ⛔ {e}")
            self._running = False
            return
        self._running = True
        print(f"[consol] ✅ GNOME запущен (PID={self._gui_proc.pid})")
        for name in LOG_FILES_TO_WATCH:
            path = os.path.join(LOGS_DIR, name)
            try:
                self._log_positions[name] = (
                    os.path.getsize(path) if os.path.isfile(path) else 0
                )
            except Exception:
                self._log_positions[name] = 0
        self._log_thread = threading.Thread(target=self._watch_logs, daemon=True)
        self._log_thread.start()
        self._monitor_thread = threading.Thread(target=self._monitor_gui, daemon=True)
        self._monitor_thread.start()
        print("[consol] Логи интерфейса видны в этой консоли\n")

    def _watch_logs(self):
        while self._running:
            time.sleep(0.5)
            for name in LOG_FILES_TO_WATCH:
                path = os.path.join(LOGS_DIR, name)
                if not os.path.isfile(path):
                    continue
                try:
                    size = os.path.getsize(path)
                    last = self._log_positions.get(name, 0)
                    if size > last:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last)
                            new = f.read()
                        self._log_positions[name] = size
                        for line in new.strip().splitlines():
                            if line:
                                print(f"\n[GUI/{name.replace('.log','')}] {line}")
                    elif size < last:
                        self._log_positions[name] = 0
                except Exception:
                    pass

    def _monitor_gui(self):
        while self._running:
            if self._gui_proc is None:
                break
            if self._gui_proc.poll() is not None:
                print(f"\n[consol] GNOME закрыт (код={self._gui_proc.returncode})")
                self._running = False
                break
            time.sleep(1)

    def _stop_gnome(self):
        print("\n[consol] Остановка GNOME...")
        self._running = False
        if self._gui_proc and self._gui_proc.poll() is None:
            try:
                self._gui_proc.terminate()
                self._gui_proc.wait(timeout=5)
            except Exception:
                try:
                    self._gui_proc.kill()
                except Exception:
                    pass
        print("[consol] GNOME остановлен")

    def _send_to_gui(self, cmd):
        cmd = cmd.strip()
        if not cmd:
            return
        print(f"[consol→GUI] {cmd}")
        cmd_file = os.path.join(LOGS_DIR, "gui_commands.txt")
        try:
            with open(cmd_file, "a", encoding="utf-8") as f:
                f.write(cmd + "\n")
        except Exception as e:
            print(f"[consol] ⛔ {e}")

    def _show_logs(self):
        print("\n" + "=" * 60)
        print("  Логи интерфейса")
        print("=" * 60)
        for name in LOG_FILES_TO_WATCH:
            path = os.path.join(LOGS_DIR, name)
            if not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                tail = lines[-20:]
                if not tail:
                    continue
                print(f"\n─── {name} ───")
                for line in tail:
                    print(f"  {line.rstrip()}")
            except Exception:
                pass
        print("\n" + "=" * 60 + "\n")

    def _clear_logs(self):
        print("[consol] Очистка логов...")
        count = 0
        for name in LOG_FILES_TO_WATCH:
            path = os.path.join(LOGS_DIR, name)
            if os.path.isfile(path):
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write("")
                    self._log_positions[name] = 0
                    count += 1
                except Exception:
                    pass
        print(f"[consol] ✅ Очищено {count} логов")

    def _print_help(self, kernel):
        print("\nКоманды ядра:")
        for name, cmd in sorted(kernel.commands.items()):
            print(f"  {name:<12} {cmd.description}")
        print("\n/команды ядра:")
        for name, entry in sorted(kernel.slash_commands.items()):
            print(f"  /{name:<12} {entry['description']}")
        print("\nGNOME Consol:")
        print("  logs                — показать логи")
        print("  clear_logs          — очистить логи")
        print("  /gnome <команда>    — команда GNOME")
        print("  user <имя>          — сменить пользователя")
        print("  exit                — выход")
        print()


def slash_gconsol(kernel, args):
    iface = GnomeConsol()
    if args:
        iface.username = args[0]
        print(f"[gconsol] Пользователь: {iface.username}")
    kernel.run_interface(iface)


def register(kernel):
    kernel.register_interface(GnomeConsol(),
                              aliases=["gconsol", "gnome_consol"])
    kernel.register_slash_command(
        "gconsol", slash_gconsol, "GNOME Consol — /gconsol [username]")
    return []
