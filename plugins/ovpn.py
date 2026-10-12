"""
OpenVPN-клиент ядра DreamUX.
Скачивает os_proxy.ovpn из репозитория DreamUxFourOVPN автоматически.

Пути:
  конфиги, ключи, .ovpn, .auth  →  ../ovpn/files/
  логи                          →  ../ovpn/logs/
"""

import os
import time
import shutil
import platform
import subprocess
import threading
import datetime
import glob
import urllib.request


PLATFORM = platform.system()

# ---------- Пути ----------
HERE = os.path.dirname(os.path.abspath(__file__))
KERNEL_DIR = os.path.dirname(HERE)
OVPN_DIR = os.path.join(KERNEL_DIR, "ovpn")
OVPN_FILES = os.path.join(OVPN_DIR, "files")
OVPN_LOGS = os.path.join(OVPN_DIR, "logs")


# ---------- Репозиторий с конфигами VPN ----------
OVPN_REPO_BASE = "https://raw.githubusercontent.com/dream-companyx/DreamUxFourOVPN/main"

# Что скачать: имя в ovpn/files/ -> URL
OVPN_DOWNLOADS = {
    "os_proxy.ovpn": f"{OVPN_REPO_BASE}/os_proxy.ovpn",
}


def _ensure_dirs():
    os.makedirs(OVPN_FILES, exist_ok=True)
    os.makedirs(OVPN_LOGS, exist_ok=True)


_ensure_dirs()


def _download(url, dst, force=False):
    if os.path.isfile(dst) and not force:
        return True
    try:
        print(f"[OVPN] Скачиваю: {os.path.basename(dst)}")
        req = urllib.request.Request(
            url, headers={"User-Agent": "DreamUX-OVPN/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        head = data[:300].lower()
        if b"<html" in head or b"404: not found" in head:
            print(f"[OVPN] Ошибка {os.path.basename(dst)}: HTML/404")
            return False
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        print(f"[OVPN] OK {os.path.basename(dst)} ({len(data)} байт)")
        return True
    except Exception as e:
        print(f"[OVPN] Ошибка {os.path.basename(dst)}: {e}")
        return False


def _download_all_ovpn(force=False):
    """Скачивает все .ovpn из репозитория."""
    for name, url in OVPN_DOWNLOADS.items():
        dst = os.path.join(OVPN_FILES, name)
        _download(url, dst, force=force)


def _update_missing_ovpn():
    """Скачивает только отсутствующие .ovpn."""
    for name, url in OVPN_DOWNLOADS.items():
        dst = os.path.join(OVPN_FILES, name)
        if not os.path.isfile(dst):
            _download(url, dst)


class OVPNClient:
    def __init__(self, log_fn=None, config_name: str = None):
        self.log_fn = log_fn or (lambda m: None)
        self.openvpn_path = None
        self.config_path = None
        self.auth_path = None
        self.proc = None
        self.connected = False
        self.kill_switch = True
        self.dns_servers = ["10.8.0.1"]
        self._lock = threading.Lock()
        self._stop = False
        self._monitor_thread = None
        self._debug_fh = None
        self._log_file = os.path.join(OVPN_LOGS, "ovpn.log")
        self._debug_log = os.path.join(OVPN_LOGS, "ovpn-debug.log")

        # Скачиваем конфиги перед первым использованием
        _update_missing_ovpn()

        self._find_openvpn()
        self._find_config(config_name)

    # ---------- Логи ----------
    def _file_log(self, msg, level="INFO"):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts}  [{level:<6}]  {msg}\n")
        except Exception:
            pass

    def log(self, msg, level="INFO"):
        self.log_fn(msg)
        self._file_log(msg, level)

    # ---------- Поиск ----------
    def _find_openvpn(self):
        self.openvpn_path = shutil.which("openvpn")
        if not self.openvpn_path and PLATFORM == "Windows":
            for p in [
                r"C:\Program Files\OpenVPN\bin\openvpn.exe",
                r"C:\Program Files (x86)\OpenVPN\bin\openvpn.exe",
            ]:
                if os.path.isfile(p):
                    self.openvpn_path = p
                    break
        elif not self.openvpn_path and PLATFORM == "Linux":
            for p in ["/usr/sbin/openvpn", "/usr/bin/openvpn"]:
                if os.path.isfile(p):
                    self.openvpn_path = p
                    break

        if self.openvpn_path:
            self.log(f"[OVPN] openvpn: {self.openvpn_path}")
        else:
            self.log("[OVPN] openvpn не найден — VPN недоступен", "WARN")

    def _find_config(self, config_name=None):
        if config_name:
            p = os.path.join(OVPN_FILES, config_name)
            if os.path.isfile(p):
                self.config_path = p
            else:
                self.log(f"[OVPN] Не найден: {p}", "WARN")
                return
        else:
            found = sorted(glob.glob(os.path.join(OVPN_FILES, "*.ovpn")))
            if not found:
                self.log(f"[OVPN] Нет .ovpn в {OVPN_FILES}", "WARN")
                return
            self.config_path = found[0]

        self.log(f"[OVPN] Конфиг: {self.config_path}")

        base = os.path.splitext(self.config_path)[0]
        for candidate in (base + ".auth", "vpn.auth", "auth.txt"):
            p = os.path.join(OVPN_FILES, candidate)
            if os.path.isfile(p):
                self.auth_path = p
                self.log(f"[OVPN] Auth: {p}")
                break

    # ---------- Подключение ----------
    def connect(self) -> bool:
        with self._lock:
            if self.connected:
                return True
            if not self.openvpn_path:
                self.log("[OVPN] openvpn не установлен", "ERROR")
                return False

            # Повторно проверяем наличие .ovpn
            if not self.config_path or not os.path.isfile(self.config_path):
                _update_missing_ovpn()
                self._find_config()

            if not self.config_path or not os.path.isfile(self.config_path):
                self.log("[OVPN] Нет .ovpn конфига", "ERROR")
                return False

            cmd = [self.openvpn_path, "--config", self.config_path, "--verb", "3"]
            if self.auth_path:
                cmd += ["--auth-user-pass", self.auth_path]

            self.log("[OVPN] Запуск туннеля...")
            try:
                self._debug_fh = open(self._debug_log, "a", encoding="utf-8")
                self._debug_fh.write(
                    f"\n===== {datetime.datetime.now()} =====\n"
                )
                self._debug_fh.flush()
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except Exception as e:
                self.log(f"[OVPN] Ошибка запуска: {e}", "ERROR")
                return False

            self._wait_for_connect(timeout=30)
            if not self.connected:
                self.log("[OVPN] Не удалось подключиться", "ERROR")
                self.disconnect()
                return False

            self._stop = False
            self._monitor_thread = threading.Thread(
                target=self._monitor, daemon=True
            )
            self._monitor_thread.start()
            self.log("[OVPN] Туннель поднят", "INFO")
            return True

    def _wait_for_connect(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            if self.proc is None or self.proc.poll() is not None:
                return
            try:
                line = self.proc.stdout.readline()
            except Exception:
                return
            if not line:
                time.sleep(0.05)
                continue
            try:
                if self._debug_fh:
                    self._debug_fh.write(line)
                    self._debug_fh.flush()
            except Exception:
                pass
            if "Initialization Sequence Completed" in line:
                self.connected = True
                return
            if "AUTH_FAILED" in line:
                self.log("[OVPN] AUTH_FAILED — неверный логин/пароль", "ERROR")
                return
            if "Cannot open" in line or "Options error" in line:
                self.log(f"[OVPN] Ошибка конфига: {line.strip()}", "ERROR")
                return
            time.sleep(0.05)

    def _monitor(self):
        while not self._stop:
            if self.proc is None:
                break
            if self.proc.poll() is not None:
                self.log("[OVPN] Процесс завершился — kill-switch", "WARN")
                self.connected = False
                break
            time.sleep(2)

    def disconnect(self):
        with self._lock:
            self._stop = True
            if self.proc:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=5)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
                self.proc = None
            try:
                if self._debug_fh:
                    self._debug_fh.close()
                    self._debug_fh = None
            except Exception:
                pass
            self.connected = False
            self.log("[OVPN] Туннель закрыт", "INFO")

    def is_connected(self) -> bool:
        return (self.connected and self.proc is not None
                and self.proc.poll() is None)

    def http_proxy(self) -> str:
        return os.environ.get("SIMPLEOS_VPN_PROXY", "")

    def status(self) -> dict:
        return {
            "available":   self.openvpn_path is not None,
            "openvpn":     self.openvpn_path,
            "config":      self.config_path,
            "auth":        self.auth_path,
            "files_dir":   OVPN_FILES,
            "logs_dir":    OVPN_LOGS,
            "log_file":    self._log_file,
            "debug_log":   self._debug_log,
            "connected":   self.is_connected(),
            "kill_switch": self.kill_switch,
            "dns":         self.dns_servers,
        }
