#!/usr/bin/env python3
"""DreamUX Setup Wizard — создаёт 3 VHD + форматирует в DRXFS."""

import os
import sys
import json
import time
import hashlib
import getpass
import subprocess
import threading
import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QProgressBar, QTextEdit,
    QStackedWidget, QMessageBox,
)


_HERE = os.path.dirname(os.path.abspath(__file__))
VFS_ROOT = os.path.join(_HERE, "vfs")
VFS_CONFIG = os.path.join(VFS_ROOT, "disks.json")
USERS_FILE = os.path.join(_HERE, "users.json")
PLUGINS_DIR = os.path.join(_HERE, "plugins")

sys.path.insert(0, PLUGINS_DIR)
from drxfs import DrxFS, _timestamp


DISKS = {
    "disk0": {
        "name": "СИСТЕМА",
        "file": os.path.join(VFS_ROOT, "disk0.vhd"),
        "size_mb": 4096,
        "subdirs": [
            "system", "system/kernel", "system/plugins", "system/config",
            "system/logs", "system/users", "system/assets", "system/bin",
            "system/lib", "system/boot",
        ],
    },
    "disk1": {
        "name": "ЗАГРУЗОЧНЫЙ",
        "file": os.path.join(VFS_ROOT, "disk1.vhd"),
        "size_mb": 3072,
        "subdirs": [
            "boot", "boot/init", "boot/recovery", "boot/efi", "boot/splash",
        ],
    },
    "disk2": {
        "name": "ОСТАЛЬНОЕ",
        "file": os.path.join(VFS_ROOT, "disk2.vhd"),
        "size_mb": 100 * 1024,
        "subdirs": [
            "home", "home/user", "apps", "packages", "downloads",
            "documents", "music", "pictures", "videos",
            "snapshots", "sandbox", "tmp", "data",
        ],
    },
}


def _is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_diskpart(script, timeout=600):
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        r = subprocess.run(
            ["diskpart"], input=script, text=True,
            capture_output=True, encoding="cp866", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo, timeout=timeout,
        )
        out = (r.stdout or "") + (r.stderr or "")
        low = out.lower()
        fatal = [
            "virtual disk service error",
            "ошибка службы виртуальных дисков",
            "the operation failed",
            "операция не выполнена",
            "не удалось",
            "не найден",
            "not found",
            "отказано в доступе",
            "access is denied",
        ]
        for m in fatal:
            if m in low:
                return False, out
        return True, out
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, f"exception: {e}"


def _create_vhd_file(path, size_mb):
    if os.path.isfile(path):
        return True, "exists"
    script = f'create vdisk file="{path}" maximum={size_mb} type=expandable\n'
    return _run_diskpart(script)


class WizardWorker(QObject):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def __init__(self, username, password):
        super().__init__()
        self.username = username
        self.password = password

    def run(self):
        try:
            self._check_admin()
            self._create_account()
            self._create_vhds()
            self._format_drxfs()
            self._populate_structure()
            self._copy_kernel_and_plugins()
            self._save_manifest()
            self.done.emit(True, "Готово")
        except Exception as e:
            import traceback
            self.log.emit(traceback.format_exc())
            self.done.emit(False, str(e))

    def _check_admin(self):
        if not _is_admin():
            raise Exception("Требуются права администратора")
        self.log.emit("[SETUP] ✅ Права администратора есть")

    def _create_account(self):
        self.progress.emit(5, "Создание аккаунта...")
        self.log.emit(f"[SETUP] Создаю аккаунт: {self.username}")
        password_hash = hashlib.sha256(self.password.encode("utf-8")).hexdigest()
        users = {}
        if os.path.isfile(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    users = json.load(f)
            except Exception:
                pass
        users[self.username.lower()] = {
            "level": 0,
            "password_hash": password_hash,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if "admin" not in users:
            users["admin"] = {"level": 1, "password_hash": None}
        if "guest" not in users:
            users["guest"] = {"level": 3, "password_hash": None}
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        self.log.emit(f"[SETUP] ✅ Аккаунт '{self.username}' создан")

    def _create_vhds(self):
        os.makedirs(VFS_ROOT, exist_ok=True)
        total = len(DISKS)
        for i, (key, info) in enumerate(DISKS.items()):
            pct = 10 + int(i * 20 / total)
            self.progress.emit(pct, f"Создание {key}...")
            self.log.emit(f"\n[SETUP] Создаю {key} ({info['size_mb']} МБ)...")
            path = info["file"]
            if os.path.isfile(path):
                self.log.emit(f"[SETUP] {key}: файл уже есть")
                continue
            ok, out = _create_vhd_file(path, info["size_mb"])
            for line in out.splitlines():
                self.log.emit(f"  | {line}")
            if not ok:
                raise Exception(f"diskpart {key} failed")
            self.log.emit(f"[SETUP] ✅ {key} создан")

    def _format_drxfs(self):
        total = len(DISKS)
        for i, (key, info) in enumerate(DISKS.items()):
            pct = 35 + int(i * 15 / total)
            self.progress.emit(pct, f"DRXFS: {key}...")
            self.log.emit(f"\n[SETUP] Форматирую DRXFS: {key}")
            try:
                fs = DrxFS(info["file"], log_fn=lambda m: self.log.emit(m))
                fs._format()
                self.log.emit(f"[SETUP] ✅ {key} — DRXFS")
            except Exception as e:
                raise Exception(f"DRXFS {key}: {e}")

    def _populate_structure(self):
        total = len(DISKS)
        for i, (key, info) in enumerate(DISKS.items()):
            pct = 50 + int(i * 10 / total)
            self.progress.emit(pct, f"Структура {key}...")
            self.log.emit(f"\n[SETUP] Структура {key}")
            fs = DrxFS(info["file"])
            for sub in info["subdirs"]:
                fs.mkdir(sub)
            self.log.emit(f"[SETUP] ✅ {key}: {len(info['subdirs'])} папок")

    def _copy_kernel_and_plugins(self):
        self.progress.emit(70, "Копирование ядра и плагинов...")
        self.log.emit("\n[SETUP] Копирую kernel.py и plugins/")
        fs0 = DrxFS(DISKS["disk0"]["file"])
        kernel_src = os.path.join(_HERE, "kernel.py")
        if os.path.isfile(kernel_src):
            with open(kernel_src, "rb") as f:
                fs0.write("system/kernel/kernel.py", f.read())
            self.log.emit("[SETUP] ✅ kernel.py → disk0:/system/kernel/")
        if os.path.isdir(PLUGINS_DIR):
            count = 0
            for name in os.listdir(PLUGINS_DIR):
                src = os.path.join(PLUGINS_DIR, name)
                if not os.path.isfile(src) or not name.endswith(".py"):
                    continue
                try:
                    with open(src, "rb") as f:
                        data = f.read()
                    fs0.write(f"system/plugins/{name}", data)
                    count += 1
                except Exception as e:
                    self.log.emit(f"[SETUP] ⚠ {name}: {e}")
            self.log.emit(f"[SETUP] ✅ plugins/ → disk0:/system/plugins/ ({count} файлов)")
        ver_src = os.path.join(_HERE, "version.json")
        if os.path.isfile(ver_src):
            with open(ver_src, "rb") as f:
                fs0.write("system/version.json", f.read())
            self.log.emit("[SETUP] ✅ version.json")
        if os.path.isfile(USERS_FILE):
            with open(USERS_FILE, "rb") as f:
                fs0.write("system/users/users.json", f.read())
            self.log.emit("[SETUP] ✅ users.json → disk0:/system/users/")

    def _save_manifest(self):
        self.progress.emit(95, "Манифест...")
        config = {
            "version": 2,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "user": self.username,
            "format": "drxfs",
            "disks": {
                key: {
                    "name": info["name"],
                    "file": info["file"],
                    "size_mb": info["size_mb"],
                    "subdirs": info["subdirs"],
                }
                for key, info in DISKS.items()
            },
        }
        with open(VFS_CONFIG, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        self.log.emit(f"\n[SETUP] ✅ Манифест: {VFS_CONFIG}")
        self.progress.emit(100, "Готово!")


class SetupWizard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DreamUX — Первая настройка")
        self.setFixedSize(720, 620)
        self.setStyleSheet("""
            QWidget { background-color: #1a1a2e; color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel#Title { font-size: 24pt; font-weight: 700; color: #4a9eff; }
            QLabel#Subtitle { font-size: 12pt; color: #8a9aaa; }
            QLabel { font-size: 11pt; }
            QLineEdit { background: #0f0f1e; border: 2px solid #2a3a5a;
                border-radius: 8px; padding: 10px; font-size: 12pt;
                color: #ffffff; }
            QLineEdit:focus { border: 2px solid #4a9eff; }
            QPushButton { background: #4a9eff; color: white; border: none;
                border-radius: 8px; padding: 12px 24px;
                font-size: 12pt; font-weight: 600; }
            QPushButton:hover { background: #5ab0ff; }
            QProgressBar { background: #0f0f1e; border: 2px solid #2a3a5a;
                border-radius: 8px; text-align: center; color: #ffffff;
                font-weight: 600; height: 24px; }
            QProgressBar::chunk { background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #4a9eff, stop:1 #a25af5); border-radius: 6px; }
            QTextEdit { background: #0a0a15; border: 2px solid #2a3a5a;
                border-radius: 8px; padding: 8px; color: #c0d0e0;
                font-family: Consolas, monospace; font-size: 9pt; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)
        title = QLabel("🌙 DreamUX")
        title.setObjectName("Title")
        layout.addWidget(title)
        subtitle = QLabel("Первая настройка системы")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_account_page())
        self.stack.addWidget(self._build_progress_page())
        self.stack.addWidget(self._build_done_page())
        self.stack.setCurrentIndex(0)

    def _build_account_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Создание аккаунта администратора:"))
        lay.addSpacing(6)
        lay.addWidget(QLabel("Имя пользователя:"))
        self.inp_user = QLineEdit(getpass.getuser())
        lay.addWidget(self.inp_user)
        lay.addWidget(QLabel("Пароль:"))
        self.inp_pass = QLineEdit()
        self.inp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.inp_pass)
        lay.addWidget(QLabel("Повторите пароль:"))
        self.inp_pass2 = QLineEdit()
        self.inp_pass2.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.inp_pass2)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet("color: #ff6b6b;")
        lay.addWidget(self.lbl_error)
        lay.addStretch()
        btn = QPushButton("Далее →")
        btn.clicked.connect(self._start)
        lay.addWidget(btn)
        return page

    def _build_progress_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)
        lay.addWidget(QLabel("Создание системы..."))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        lay.addWidget(self.progress)
        self.lbl_status = QLabel("Подготовка...")
        self.lbl_status.setStyleSheet("color: #8a9aaa; font-size: 10pt;")
        lay.addWidget(self.lbl_status)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        lay.addWidget(self.txt_log, 1)
        return page

    def _build_done_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(16)
        icon = QLabel("✅")
        icon.setStyleSheet("font-size: 64pt;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)
        title = QLabel("Система готова!")
        title.setStyleSheet("font-size: 20pt; font-weight: 700; color: #6bff6b;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        info = QLabel(
            "DreamUX настроена.\n\n"
            "Созданы 3 VHD с DRXFS:\n"
            "  💽 disk0.vhd — СИСТЕМА (4 ГБ)\n"
            "  💾 disk1.vhd — ЗАГРУЗОЧНЫЙ (3 ГБ)\n"
            "  🗄 disk2.vhd — ОСТАЛЬНОЕ (100 ГБ)\n\n"
            "VHD не монтируются в Windows.\n"
            "DreamUX читает/пишет напрямую."
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #a0b0c0; font-size: 11pt;")
        lay.addWidget(info)
        lay.addSpacing(20)
        btn = QPushButton("Завершить")
        btn.clicked.connect(lambda: QApplication.instance().quit())
        lay.addWidget(btn)
        return page

    def _start(self):
        user = self.inp_user.text().strip()
        pwd = self.inp_pass.text()
        pwd2 = self.inp_pass2.text()
        if not user:
            self.lbl_error.setText("Введите имя")
            return
        if len(pwd) < 4:
            self.lbl_error.setText("Пароль минимум 4 символа")
            return
        if pwd != pwd2:
            self.lbl_error.setText("Пароли не совпадают")
            return
        if not _is_admin():
            QMessageBox.critical(self, "Ошибка",
                "Требуются права администратора.")
            return
        self.lbl_error.setText("")
        self.stack.setCurrentIndex(1)
        self.worker = WizardWorker(user, pwd)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._on_log)
        self.worker.done.connect(self._on_done)
        threading.Thread(target=self.worker.run, daemon=True).start()

    def _on_progress(self, v, s):
        self.progress.setValue(v)
        if s:
            self.lbl_status.setText(s)

    def _on_log(self, line):
        self.txt_log.append(line)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_done(self, ok, msg):
        if ok:
            QTimer.singleShot(500, lambda: self.stack.setCurrentIndex(2))
        else:
            self.lbl_status.setText(f"❌ Ошибка: {msg}")
            QMessageBox.critical(self, "Ошибка", msg)


def main():
    app = QApplication(sys.argv)
    w = SetupWizard()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
