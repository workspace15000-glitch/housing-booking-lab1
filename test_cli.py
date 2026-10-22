"""Проверки восстановления меню после ошибочного и прерванного ввода."""

from contextlib import redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from housing_booking.cli import ConsoleApp
from housing_booking.demo import create_demo
from housing_booking.exceptions import StorageError
from housing_booking.serialization import snapshot


class ConsoleTests(unittest.TestCase):
    def run_menu(self, answers, app=None):
        app = app if app is not None else ConsoleApp()
        output = StringIO()
        with patch("builtins.input", side_effect=answers), redirect_stdout(output):
            app.run()
        return app, output.getvalue()

    def test_invalid_menu_selection_recovers(self):
        app, output = self.run_menu(["не пункт", "6", "0"])
        self.assertIn("Выберите пункт от 0 до 6", output)
        self.assertEqual(len(app.system.list("accommodations")), 3)
        self.assertIn("До свидания", output)

    def test_invalid_number_and_date_return_to_menu(self):
        for answers in (["1", "не число", "6", "0"],
                        ["2", "2026-99-99", "6", "0"]):
            with self.subTest(answers=answers):
                app, output = self.run_menu(answers)
                self.assertIn("Ошибка:", output)
                self.assertIn("Загружен пример", output)
                self.assertEqual(len(app.system.list("bookings")), 3)

    def test_invalid_price_does_not_add_partial_housing(self):
        app = ConsoleApp()
        app.system = create_demo()
        before = snapshot(app.system)
        answers = ["1", "4", "3", "new", "apartment", "Москва", "Улица", "1",
                   "h1", "Квартира", "не цена", "0"]
        _, output = self.run_menu(answers, app)
        self.assertIn("Ошибка:", output)
        self.assertIn("До свидания", output)
        self.assertEqual(snapshot(app.system), before)

    def test_demo_and_booking_list_show_total_cost(self):
        app, output = self.run_menu(["6", "1", "5", "1", "0"])
        self.assertIn('"id": "b1"', output)
        self.assertIn("Стоимость проживания: 10500.00 руб.", output)
        self.assertEqual(len(app.system.list("bookings")), 3)

    def test_failed_load_preserves_system_and_returns_to_menu(self):
        for format_name, storage_class in (("json", "JsonStorage"), ("xml", "XmlStorage")):
            with self.subTest(format=format_name):
                app = ConsoleApp()
                app.system = create_demo()
                original, before = app.system, snapshot(app.system)
                target = f"housing_booking.cli.{storage_class}.load"
                with patch(target, side_effect=StorageError("Файл повреждён")):
                    _, output = self.run_menu(["5", format_name, "broken.file", "да", "0"], app)
                self.assertIs(app.system, original)
                self.assertEqual(snapshot(app.system), before)
                self.assertIn("Ошибка: Файл повреждён", output)
                self.assertIn("До свидания", output)

    def test_eof_and_interrupt_exit_cleanly(self):
        for error in (EOFError, KeyboardInterrupt):
            for prefix in ([], ["1", "4", "3"]):
                with self.subTest(error=error.__name__, prefix=prefix):
                    app = ConsoleApp()
                    app.system = create_demo()
                    before = snapshot(app.system)
                    _, output = self.run_menu([*prefix, error], app)
                    self.assertIn("Работа завершена", output)
                    self.assertEqual(snapshot(app.system), before)


if __name__ == "__main__":
    unittest.main()
