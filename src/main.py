"""Backward-compatible CLI entrypoint.

Use `python -m src.main_text ...` for the dedicated text parser command.
"""

from src.main_text import main


if __name__ == "__main__":
    main()
