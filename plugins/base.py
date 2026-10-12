"""Базовые классы плагинов DreamUX."""

import os
import subprocess


class Command:
    name: str = ""
    description: str = ""
    usage: str = ""

    def run(self, kernel, args: list[str]) -> None:
        raise NotImplementedError


class Interface:
    name: str = ""
    description: str = ""
    id: int = 0

    def render(self, kernel) -> None:
        raise NotImplementedError

    def handle_input(self, kernel, line: str) -> bool:
        return True


class App:
    """
    Плагин-приложение.
    Оболочка (.py/.dll) регистрирует приложение в ядре.
    .exe (опционально) — само приложение.
    """
    name: str = ""
    icon: str = "📦"
    description: str = ""
    exe_name: str = ""
    mode: str = "inproc"

    def get_dir(self) -> str:
        return os.path.dirname(os.path.abspath(__file__))

    def get_exe_path(self) -> str:
        return os.path.join(self.get_dir(), self.exe_name)

    def open(self, desktop, kernel=None):
        if self.mode == "subprocess":
            return self._open_subprocess()
        return self._open_inproc(desktop, kernel)

    def _open_subprocess(self):
        exe = self.get_exe_path()
        if not os.path.isfile(exe):
            print(f"[APP] {self.name}: не найден {exe}")
            return
        try:
            proc = subprocess.Popen([exe], cwd=self.get_dir())
            print(f"[APP] {self.name} запущен (PID={proc.pid})")
        except Exception as e:
            print(f"[APP] {self.name}: {e}")

    def _open_inproc(self, desktop, kernel):
        raise NotImplementedError(
            f"{self.__class__.__name__}: реализуй _open_inproc()"
        )
