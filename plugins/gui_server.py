"""GUI Server — плагин. Запускает gnome_gui.py и связывает с ядром."""

import os
import sys
import io
import json
import time
import socket
import threading
import subprocess


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(PLUGIN_DIR)
GNOME_DIR = os.path.join(PLUGIN_DIR, "gnome_gui")
GUI_FILE = os.path.join(GNOME_DIR, "gnome_gui.py")
LOGS_DIR = os.path.join(GNOME_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(GNOME_DIR, "screenshots")
ASSETS_DIR = os.path.join(GNOME_DIR, "assets")

GUI_HOST = "127.0.0.1"
GUI_PORT = 54325
GUI_TOKEN = "dreamux_gui_secret_2024"


class GUIServer:
    def __init__(self, kernel):
        self.kernel = kernel
        self.running = False
        self.gui_proc = None
        self._server = None
        self._threads = []

    def start_gui(self):
        if self.gui_proc is not None and self.gui_proc.poll() is None:
            print(f"[GUI] Уже запущен (PID={self.gui_proc.pid})")
            return True
        if not os.path.isfile(GUI_FILE):
            print(f"[GUI] ⛔ Не найден: {GUI_FILE}")
            return False
        try:
            import PyQt6  # noqa
        except ImportError:
            print("[GUI] ⛔ PyQt6 не установлен")
            return False
        for d in (LOGS_DIR, SCREENSHOTS_DIR, ASSETS_DIR):
            try:
                os.makedirs(d, exist_ok=True)
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
        env["SIMPLEOS_SCREENSHOTS_DIR"] = SCREENSHOTS_DIR
        env["SIMPLEOS_ASSETS_DIR"] = ASSETS_DIR
        env["DREAMUX_GUI_SERVER"] = f"{GUI_HOST}:{GUI_PORT}"
        env["DREAMUX_GUI_TOKEN"] = GUI_TOKEN
        log_path = os.path.join(LOGS_DIR, "gnome_stderr.log")
        try:
            log_f = open(log_path, "w", encoding="utf-8")
            self.gui_proc = subprocess.Popen(
                [sys.executable, GUI_FILE],
                cwd=GNOME_DIR, env=env,
                stdout=log_f, stderr=subprocess.STDOUT,
            )
            print(f"[GUI] ✅ Запущен (PID={self.gui_proc.pid})")
            return True
        except Exception as e:
            print(f"[GUI] ⛔ Ошибка: {e}")
            self.gui_proc = None
            return False

    def stop_gui(self):
        if self.gui_proc is None or self.gui_proc.poll() is not None:
            print("[GUI] Не запущен")
            self.gui_proc = None
            return
        try:
            self.gui_proc.terminate()
            self.gui_proc.wait(timeout=5)
            print("[GUI] Остановлен")
        except Exception:
            try:
                self.gui_proc.kill()
            except Exception:
                pass
        self.gui_proc = None

    def start_server(self):
        if self.running:
            return
        self.running = True
        t = threading.Thread(target=self._serve, daemon=True)
        t.start()
        self._threads.append(t)
        print(f"[GUI] Server: {GUI_HOST}:{GUI_PORT}")

    def _serve(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind((GUI_HOST, GUI_PORT))
        except OSError as e:
            print(f"[GUI] ⛔ Порт {GUI_PORT}: {e}")
            self.running = False
            return
        self._server.listen(5)
        self._server.settimeout(1.0)
        while self.running:
            try:
                conn, addr = self._server.accept()
                threading.Thread(target=self._handle_client,
                                 args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[GUI] accept: {e}")
        try:
            self._server.close()
        except Exception:
            pass

    def _handle_client(self, conn, addr):
        try:
            conn.settimeout(300)
            buffer = b""
            while self.running:
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        request = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    response = self._process_request(request)
                    try:
                        conn.sendall(
                            json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"
                        )
                    except Exception:
                        break
        except Exception as e:
            print(f"[GUI] client: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _process_request(self, request):
        if request.get("token") != GUI_TOKEN:
            return {"ok": False, "error": "bad token"}
        cmd = (request.get("cmd") or "").strip()
        if not cmd:
            return {"ok": False, "error": "empty command"}
        old_out = sys.stdout
        old_err = sys.stderr
        buf = io.StringIO()
        sys.stdout = buf
        sys.stderr = buf
        try:
            self._run_command(cmd)
            return {"ok": True, "output": buf.getvalue()}
        except Exception as e:
            import traceback
            return {
                "ok": False,
                "error": str(e),
                "output": buf.getvalue() + "\n" + traceback.format_exc(),
            }
        finally:
            sys.stdout = old_out
            sys.stderr = old_err

    def _run_command(self, cmd):
        kernel = self.kernel
        if cmd.startswith("/"):
            parts = cmd[1:].split()
            if not parts:
                print("Пустая /команда")
                return
            token = parts[0].lower()
            args = parts[1:]
            if token in ("gnome", "gconsol", "gui"):
                print("[GUI] Команда уже выполнена при старте системы")
                return
            entry = kernel.slash_commands.get(token)
            if entry is None:
                print(f"Неизвестная /команда: /{token}")
                return
            entry["handler"](kernel, args)
            return
        parts = cmd.split()
        name, args = parts[0], parts[1:]
        obj = kernel.commands.get(name)
        if obj is None:
            print(f"Неизвестная команда: {name}")
            return
        obj.run(kernel, args)

    def shutdown(self):
        self.running = False
        self.stop_gui()
        try:
            if self._server:
                self._server.close()
        except Exception:
            pass


_SERVER = None


def get_server(kernel=None):
    global _SERVER
    if _SERVER is None and kernel is not None:
        _SERVER = GUIServer(kernel)
    return _SERVER


def register(kernel):
    server = GUIServer(kernel)
    global _SERVER
    _SERVER = server

    def slash_gui(kernel_, args):
        if not args:
            print("DreamUX GUI Server")
            print("  /gui start    — запустить")
            print("  /gui stop     — остановить")
            print("  /gui restart  — перезапустить")
            print("  /gui status   — статус")
            return
        cmd = args[0].lower()
        if cmd == "start":
            server.start_server()
            server.start_gui()
        elif cmd == "stop":
            server.stop_gui()
        elif cmd == "restart":
            server.stop_gui()
            time.sleep(1)
            server.start_server()
            server.start_gui()
        elif cmd == "status":
            if server.gui_proc and server.gui_proc.poll() is None:
                print(f"[GUI] 🟢 Запущен (PID={server.gui_proc.pid})")
            else:
                print("[GUI] 🔴 Не запущен")
        else:
            print(f"Неизвестно: {cmd}")

    kernel.register_slash_command("gui", slash_gui, "Управление GUI DreamUX")
    return []
