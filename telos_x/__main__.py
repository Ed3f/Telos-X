"""Command-line entry point for ``python -m telos_x``."""

from telos_x.runner import TelegramMonitorRunner


def main() -> int:
    """Run the Telos-X command-line application."""
    return TelegramMonitorRunner().main()


if __name__ == "__main__":
    raise SystemExit(main())
