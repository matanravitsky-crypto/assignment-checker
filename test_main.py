from main import get_greeting


def test_default_greeting():
    assert get_greeting() == "Hello, World!"


def test_custom_greeting():
    assert get_greeting("Student") == "Hello, Student!"


if __name__ == "__main__":
    test_default_greeting()
    test_custom_greeting()
    print("All tests passed.")
