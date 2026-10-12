"""Базовые классы для плагинов."""


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