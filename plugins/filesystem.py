from plugins.base import Command


class FsCommand(Command):
    def fs(self, kernel):
        return kernel.state.setdefault("fs", {"/": {}})

    def resolve(self, kernel, path, create=False):
        fs = self.fs(kernel)
        if path.startswith("/"):
            path = path[1:]
        parts = [p for p in path.split("/") if p]
        node = fs
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        return node, (parts[-1] if parts else None)


class LsCommand(FsCommand):
    name = "ls"
    description = "список файлов"
    usage = "ls [путь]"

    def run(self, kernel, args):
        path = args[0] if args else "/"
        node, _ = self.resolve(kernel, path)
        if not node:
            print("(пусто)")
            return
        for name in sorted(node.keys()):
            kind = "DIR " if isinstance(node[name], dict) else "FILE"
            print(f"  {kind}  {name}")


class MkdirCommand(FsCommand):
    name = "mkdir"
    description = "создать папку"
    usage = "mkdir <путь>"

    def run(self, kernel, args):
        if not args:
            print("Использование: mkdir <путь>")
            return
        node, name = self.resolve(kernel, args[0])
        if name:
            node.setdefault(name, {})


class TouchCommand(FsCommand):
    name = "touch"
    description = "создать файл"
    usage = "touch <путь>"

    def run(self, kernel, args):
        if not args:
            print("Использование: touch <путь>")
            return
        node, name = self.resolve(kernel, args[0])
        if name:
            node[name] = ""


class CatCommand(FsCommand):
    name = "cat"
    description = "прочитать файл"
    usage = "cat <файл>"

    def run(self, kernel, args):
        if not args:
            print("Использование: cat <файл>")
            return
        node, name = self.resolve(kernel, args[0])
        data = node.get(name)
        if isinstance(data, str):
            print(data)
        elif data is None:
            print(f"Нет такого файла: {args[0]}")


class WriteCommand(FsCommand):
    name = "write"
    description = "записать текст в файл"
    usage = "write <файл> <текст>"

    def run(self, kernel, args):
        if len(args) < 2:
            print("Использование: write <файл> <текст>")
            return
        path, text = args[0], " ".join(args[1:])
        node, name = self.resolve(kernel, path)
        if isinstance(node.get(name), dict):
            print("Это папка")
            return
        node[name] = text


def register(kernel):
    return [
        LsCommand(),
        MkdirCommand(),
        TouchCommand(),
        CatCommand(),
        WriteCommand(),
    ]
