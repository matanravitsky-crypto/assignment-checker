"""Assignment Checker - basic starting point."""


def get_greeting(name: str = "World") -> str:
    return f"Hello, {name}!"


def main() -> None:
    print(get_greeting())


if __name__ == "__main__":
    main()
