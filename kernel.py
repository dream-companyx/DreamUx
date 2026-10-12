#!/usr/bin/env python3
"""SimpleConsoleOS — ядро DreamUX v2.5.0."""

import os
import sys
import json
import importlib
import importlib.machinery
import importlib.util
import pkgutil


# ============================================================
# sys.path
# ============================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGINS = os.path.join(_HERE, "plugins")
_APPS = os.path.join(_PLUGINS, "apps")

for _p in (_HERE, _PLUGINS, _APPS):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)


# ============================================================
# Загрузка .dll
# ============================================================
def load_dll(module_name, dll_path):
    """Загружает .dll как Python-модуль через ExtensionFileLoader."""
    loader = importlib.machinery.ExtensionFileLoader(module_name, dll_path)
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# ============================================================
# Ядро
# ============================================================
class Kernel:
    def __init__(self):
        self.commands = {}
        self.slash_commands = {}
        self.interfaces = {}
        self.named_interfaces = {}
        self.apps = {}
        self._next_iface_id = 1
        self.loaded_plugins = []
        self.state = {}
        self.running = True

    # ---------- Регистрация ----------
    def register_command(self, cmd):
        self.commands[cmd.name] = cmd

    def register_slash_command(self, name, handler, description=""):
        name = name.lstrip("/").lower()
        self.slash_commands[name] = {
            "handler": handler,
            "description": description,
        }

    def register_interface(self, iface, aliases=None):
        iface.id = self._next_iface_id
        self.interfaces[self._next_iface_id] = iface
        self._next_iface_id += 1
        for alias in (aliases or []):
            self.named_interfaces[alias.lower()] = iface
        print(f"[KERNEL] интерфейс '{iface.name}' зарегистрирован "
              f"(id={iface.id}, aliases={aliases})")
        return iface.id

    def register_app(self, app):
        self.apps[app.name] = app
        print(f"[KERNEL] приложение '{app.name}' зарегистрировано")

    # ---------- Загрузка плагинов ----------
    def _try_load_dll(self, module_name, dll_path):
        try:
            module = load_dll(module_name, dll_path)
            print(f"[DEBUG]   {module_name}: загружен из .dll")
            return module
        except Exception as e:
            print(f"[DEBUG]   {module_name}: .dll ошибка: {e}")
            return None

    def _try_load_py(self, module_name):
        try:
            module = importlib.import_module(f"plugins.{module_name}")
            print(f"[DEBUG]   {module_name}: загружен из .py")
            return module
        except Exception as e:
            print(f"[DEBUG]   {module_name}: .py ошибка: {e}")
            return None

    def load_plugin(self, module_name):
        print(f"[DEBUG] load_plugin({module_name})")

        dll_path = os.path.join(_PLUGINS, module_name + ".dll")
        py_path = os.path.join(_PLUGINS, module_name + ".py")

        module = None

        if os.path.isfile(dll_path):
            module = self._try_load_dll(module_name, dll_path)

        if module is None and os.path.isfile(py_path):
            module = self._try_load_py(module_name)

        if module is None:
            print(f"[!] Плагин не найден: {module_name}")
            return

        if hasattr(module, "register"):
            try:
                result = module.register(self)
                for cmd in (result or []):
                    self.register_command(cmd)
            except Exception as e:
                import traceback
                print(f"[DEBUG]   register() упал:")
                traceback.print_exc()

        self.loaded_plugins.append(module_name)
        print(f"[+] Плагин загружен: {module_name}")

    def load_all_plugins(self):
        if not os.path.isdir(_PLUGINS):
            return
        for _, name, _ in pkgutil.iter_modules([_PLUGINS]):
            if name in ("base", "__init__", "apps"):
                continue
            self.load_plugin(name)

    # ---------- Загрузка приложений ----------
    def _try_load_app_dll(self, name, dll_path):
        try:
            module = load_dll(f"app_{name}", dll_path)
            print(f"[DEBUG]   app {name}: загружен из .dll")
            return module
        except Exception as e:
            print(f"[DEBUG]   app {name}: .dll ошибка: {e}")
            return None

    def _try_load_app_py(self, name, py_path):
        try:
            spec = importlib.util.spec_from_file_location(f"app_{name}", py_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            print(f"[DEBUG]   app {name}: загружен из .py")
            return module
        except Exception as e:
            print(f"[DEBUG]   app {name}: .py ошибка: {e}")
            return None

    def load_all_apps(self):
        if not os.path.isdir(_APPS):
            return

        for entry in sorted(os.scandir(_APPS), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            name = entry.name

            dll_path = os.path.join(entry.path, f"{name}.dll")
            py_path = os.path.join(entry.path, f"{name}.py")

            module = None

            if os.path.isfile(dll_path):
                module = self._try_load_app_dll(name, dll_path)

            if module is None and os.path.isfile(py_path):
                module = self._try_load_app_py(name, py_path)

            if module is None:
                print(f"[!] App {name}: нет ни .dll, ни .py")
                continue

            if hasattr(module, "register"):
                try:
                    module.register(self)
                except Exception as e:
                    import traceback
                    print(f"[DEBUG]   app {name} register() упал:")
                    traceback.print_exc()
            else:
                print(f"[!] App {name}: нет register()")

    # ---------- Баннер ----------
    def banner(self):
        print("=" * 46)
        print("   SimpleConsoleOS v2.5.0  —  DreamUX")
        print("   'help'                — список команд")
        print("   '/interface <номер>'  — интерфейс по номеру")
        print("   '/interfacegnom'      — запустить GNOME")
        print("   '/testgnome'          — диагностика GNOME")
        print("   '/update'             — проверка обновлений")
        print("   '/remote'             — RemoteTools")
        print("   '/help'               — все /команды")
        print("=" * 46)

    # ---------- Интерфейсы ----------
    def run_interface(self, iface):
        iface.render(self)
        while self.running:
            try:
                line = input(f"[{iface.name}]> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in ("/exit", "exit", "/quit", "quit"):
                break
            try:
                if iface.handle_input(self, line):
                    break
            except Exception as e:
                print(f"[ошибка интерфейса] {e}")

    # ---------- REPL ----------
    def repl(self):
        while self.running:
            try:
                line = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue

            if line.startswith("/"):
                parts = line[1:].split()
                if not parts:
                    print("Пустая /команда. Смотри /help")
                    continue
                token = parts[0].lower()
                args = parts[1:]

                if token in ("exit", "halt", "shutdown"):
                    print("Система выключена. Пока!")
                    self.running = False
                    continue

                if token == "help":
                    self._print_slash_help()
                    continue

                if token == "interface":
                    if not args or not args[0].isdigit():
                        print("Использование: /interface <номер>")
                        self._list_interfaces()
                        continue
                    iface = self.interfaces.get(int(args[0]))
                    if iface is None:
                        print(f"Нет интерфейса с номером {args[0]}")
                        self._list_interfaces()
                        continue
                    self.run_interface(iface)
                    continue

                if token.startswith("interface"):
                    name = token[len("interface"):]
                    if not name:
                        print("Использование: /interface<имя>")
                        self._list_named()
                        continue
                    iface = self.named_interfaces.get(name.lower())
                    if iface is None:
                        print(f"Нет интерфейса: /interface{name}")
                        self._list_named()
                        continue
                    self.run_interface(iface)
                    continue

                entry = self.slash_commands.get(token)
                if entry is None:
                    print(f"Неизвестная /команда: /{token}")
                    print("Список: /help")
                    continue
                try:
                    entry["handler"](self, args)
                except Exception as e:
                    import traceback
                    print(f"[ошибка /{token}] {e}")
                    traceback.print_exc()
                continue

            parts = line.split()
            name, args = parts[0], parts[1:]
            cmd = self.commands.get(name)
            if cmd is None:
                print(f"Неизвестная команда: {name}")
                continue
            try:
                cmd.run(self, args)
            except Exception as e:
                print(f"[ошибка команды] {e}")

    def _print_slash_help(self):
        print("\n/команды:")
        print(f"  {'/interface <номер>':<24} — интерфейс по номеру")
        print(f"  {'/interface<имя>':<24} — интерфейс по имени")
        print(f"  {'/help':<24} — этот список")
        print(f"  {'/exit':<24} — выключить систему")
        if self.slash_commands:
            print("\nОт плагинов:")
            for name, entry in sorted(self.slash_commands.items()):
                print(f"  {'/' + name:<24} — {entry['description']}")
        if self.named_interfaces:
            print("\nИменованные интерфейсы:")
            for name, iface in sorted(self.named_interfaces.items()):
                print(f"  /interface{name:<12} — {iface.description}")
        if self.apps:
            print("\nПриложения:")
            for name, app in sorted(self.apps.items()):
                print(f"  {app.icon} {name:<12} — {app.description}")
        print()

    def _list_interfaces(self):
        if not self.interfaces:
            print("(интерфейсов нет)")
            return
        print("Доступные интерфейсы:")
        for num, iface in sorted(self.interfaces.items()):
            print(f"  {num}. {iface.name} — {iface.description}")

    def _list_named(self):
        if not self.named_interfaces:
            print("(именованных интерфейсов нет)")
            return
        print("Именованные интерфейсы:")
        for name, iface in sorted(self.named_interfaces.items()):
            print(f"  /interface{name} — {iface.description}")

    def boot(self):
        self.banner()
        self.load_all_plugins()
        self.load_all_apps()
        print()
        self.repl()
        print("Система остановлена.")


if __name__ == "__main__":
    try:
        Kernel().boot()
    except KeyboardInterrupt:
        sys.exit(0)
