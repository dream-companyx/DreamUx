from plugins.base import Command


class HelpCommand(Command):
    name = "help"
    description = "показать список команд и интерфейсов"
    usage = "help"

    def run(self, kernel, args):
        print("\nКоманды:")
        for name, cmd in sorted(kernel.commands.items()):
            print(f"  {name:<10} - {cmd.description}")
        if kernel.interfaces:
            print("\nИнтерфейсы (запуск: /interface <номер>):")
            for num, iface in sorted(kernel.interfaces.items()):
                print(f"  {num}. {iface.name:<8} - {iface.description}")
        if kernel.named_interfaces:
            print("\nИменованные интерфейсы:")
            for name, iface in sorted(kernel.named_interfaces.items()):
                print(f"  /interface{name} - {iface.description}")
        print()


class EchoCommand(Command):
    name = "echo"
    description = "вывести текст"
    usage = "echo <текст>"

    def run(self, kernel, args):
        print(" ".join(args))


class ClearCommand(Command):
    name = "clear"
    description = "очистить экран"
    usage = "clear"

    def run(self, kernel, args):
        print("\033[2J\033[H", end="")


class HaltCommand(Command):
    name = "halt"
    description = "выключить систему"
    usage = "halt"

    def run(self, kernel, args):
        print("Система выключена. Пока!")
        kernel.running = False


class PluginsCommand(Command):
    name = "plugins"
    description = "список загруженных плагинов"
    usage = "plugins"

    def run(self, kernel, args):
        print("\nЗагруженные плагины:")
        for name in sorted(kernel.loaded_plugins):
            print(f"  • {name}")
        print()


def slash_about(kernel, args):
    print("SimpleOS v1.0 — учебная консольная ОС.")
    print("Плагины регистрируют команды, /команды и интерфейсы.")


def register(kernel):
    kernel.register_slash_command("about", slash_about, "о системе") \
        if hasattr(kernel, "register_slash_command") else None
    return [
        HelpCommand(),
        EchoCommand(),
        ClearCommand(),
        HaltCommand(),
        PluginsCommand(),
    ]