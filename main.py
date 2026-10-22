"""Точка входа: python main.py или python main.py --demo."""

import argparse

from housing_booking.cli import ConsoleApp
from housing_booking.demo import run_demo
from housing_booking.exceptions import BookingError


def main() -> None:
    parser = argparse.ArgumentParser(description="Учебная система бронирования жилья")
    parser.add_argument("--demo", action="store_true", help="Запустить готовый сценарий")
    parser.add_argument("--output-dir", default="data", help="Папка результатов демо")
    args = parser.parse_args()
    if args.demo:
        try:
            run_demo(args.output_dir)
        except BookingError as error:
            print(f"Ошибка: {error}")
            raise SystemExit(1) from error
    else:
        ConsoleApp().run()


if __name__ == "__main__":
    main()
