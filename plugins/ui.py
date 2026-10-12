from plugins.base import Interface


class NotesInterface(Interface):
    name = "notes"
    description = "заметки"

    def render(self, kernel):
        notes = kernel.state.setdefault("notes", [])
        print(f"\n=== Заметки (интерфейс #{self.id}) ===")
        if not notes:
            print("  (пусто)")
        for i, n in enumerate(notes, 1):
            print(f"  {i}. {n}")
        print("\nВнутри: add <текст>, del <номер>, /exit\n")

    def handle_input(self, kernel, line):
        notes = kernel.state.setdefault("notes", [])
        parts = line.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "add":
            notes.append(arg)
        elif cmd == "del":
            try:
                notes.pop(int(arg) - 1)
            except (ValueError, IndexError):
                print("Неверный номер")
        self.render(kernel)
        return False


class ClockInterface(Interface):
    name = "clock"
    description = "часы"

    def render(self, kernel):
        import time
        print(f"\n=== Часы (интерфейс #{self.id}) ===")
        print("  " + time.strftime("%H:%M:%S"))
        print("  'tick' — обновить, /exit — выйти\n")

    def handle_input(self, kernel, line):
        if line == "tick":
            self.render(kernel)
        return False


def register(kernel):
    kernel.register_interface(NotesInterface(), aliases=["notes"])
    kernel.register_interface(ClockInterface(), aliases=["clock"])
    return []
