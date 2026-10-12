#!/usr/bin/env python3
"""SimpleConsoleOS — ядро DreamUX."""

import os
import sys

# --- sys.path ---
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    _HERE,
    os.path.join(_HERE, "plugins"),
    os.path.join(_HERE, "plugins", "gnome_gui"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import importlib
import pkgutil

import plugins


class Kernel:
    def __init__(self):
        self.commands = {}
        self.slash_commands = {}
        self.interfaces = {}
        self.named_interfaces = {}
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

    # ---------- Плагины ----------
    def load_plugin(self, module_name):
        print(f"[DEBUG] load_plugin({module_name})")
        try:
            module = importlib.import_module(f"plugins.{module_name}")
            print(f"[DEBUG]   файл: {getattr(module, '__file__', '?')}")
        except Exception as e:
            print(f"[!] Не удалось загрузить '{module_name}': {e}")
            return

        if hasattr(module, "register"):
            print(f"[DEBUG]   register() найден, вызываю...")
            try:
                result = module.register(self)
                print(f"[DEBUG]   register() вернул: {result}")
                for cmd in (result or []):
                    self.register_command(cmd)
            except Exception as e:
                import traceback
                print(f"[DEBUG]   ⛔ register() упал:")
                traceback.print_exc()
        else:
            print(f"[DEBUG]   ⚠ register() отсутствует")

        self.loaded_plugins.append(module_name)
        print(f"[+] Плагин загружен: {module_name}")

    def load_all_plugins(self):
        for _, name, _ in pkgutil.iter_modules(plugins.__path__):
            if name in ("base", "__init__", "gnome_gui"):
                continue
            self.load_plugin(name)

    # ---------- Баннер ----------
    def banner(self):
        print("=" * 46)
        print("   SimpleConsoleOS v1.0")
        print("   'help'                — список команд")
        print("   '/interface <номер>'  — интерфейс по номеру")
        print("   '/interfacegnom'      — запустить GNOME")
        print("   '/testgnome'          — диагностика GNOME")
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
                    print(f"[ошибка /{token}] {e}")
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
        print()
        self.repl()
        print("Система остановлена.")


if __name__ == "__main__":
    try:
        Kernel().boot()
    except KeyboardInterrupt:
        sys.exit(0)