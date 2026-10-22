"""Русскоязычное меню: CRUD, поиск и работа с файлами."""

from dataclasses import fields
from decimal import InvalidOperation
import json
from pathlib import Path

from .demo import create_demo
from .exceptions import BookingError, ValidationError
from .forms import EntityForm, ask, read_period
from .serialization import encode
from .service import BookingSystem
from .storage import DataStorage, JsonStorage, XmlStorage


class ConsoleApp:
    """Повторяет меню после ошибки пользователя, не теряя состояние."""

    def __init__(self) -> None:
        self.system = BookingSystem()

    def run(self) -> None:
        print("Бронирование жилья. Сначала загрузите пример или добавьте данные.")
        while True:
            try:
                print("\n1 Данные (CRUD) | 2 Поиск жилья | 3 Отменить бронь")
                print("4 Сохранить | 5 Загрузить | 6 Демоданные | 0 Выход")
                choice = input("> ").strip()
                if choice == "0":
                    print("До свидания! Несохранённые изменения не записываются.")
                    return
                if choice == "1":
                    self._crud()
                elif choice == "2":
                    self._search()
                elif choice == "3":
                    self.system.cancel_booking(ask("ID брони"))
                    print("Бронь отменена.")
                elif choice in ("4", "5"):
                    self._file(choice == "4")
                elif choice == "6":
                    if self._confirm_replace():
                        self.system = create_demo()
                        print("Загружен пример: хозяин h1, гость g1, жильё a1/h2/r1.")
                else:
                    print("Выберите пункт от 0 до 6.")
            except (BookingError, ValueError, TypeError, InvalidOperation) as error:
                print(f"Ошибка: {error}")
            except (EOFError, KeyboardInterrupt):
                print("\nРабота завершена. Сохраняйте изменения через пункт 4.")
                return

    def _crud(self) -> None:
        names = ("Хозяева", "Гости", "Удобства", "Жильё", "Брони", "Отзывы")
        for index, name in enumerate(names, 1):
            print(f"{index} {name}")
        number = ask("Коллекция", int)
        if number not in range(1, 7):
            raise ValidationError("Выберите коллекцию от 1 до 6.")
        collection = self.system.COLLECTIONS[number - 1]
        print("1 Список | 2 Просмотр по ID | 3 Добавить | 4 Изменить | 5 Удалить")
        operation = ask("Операция")
        if operation == "1":
            objects = self.system.list(collection)
            if not objects:
                print("Пока нет записей.")
            for entity in objects:
                self._show(entity)
        elif operation == "2":
            self._show(self.system.get(collection, ask("ID")))
        elif operation == "3":
            entity = EntityForm(self.system).read(collection)
            self.system.add(entity)
            print(f"Создано: {entity.id}")
        elif operation == "4":
            original = self.system.get(collection, ask("ID"))
            print("Пустой ответ оставляет прежнее значение.")
            updated = EntityForm(self.system).read(collection, original)
            changes = {
                field.name: getattr(updated, field.name)
                for field in fields(updated)
                if field.name not in ("id", "nightly_price")
            }
            self.system.update(collection, original.id, **changes)
            print("Изменения сохранены в памяти.")
        elif operation == "5":
            entity_id = ask("ID")
            if ask("Удалить запись? да/нет") == "да":
                self.system.delete(collection, entity_id)
                print("Запись удалена.")
        else:
            raise ValidationError("Выберите операцию от 1 до 5.")

    @staticmethod
    def _show(entity: object) -> None:
        print(json.dumps(encode(entity), ensure_ascii=False, indent=2))
        if hasattr(entity, "total_price"):
            print(f"Стоимость проживания: {entity.total_price:.2f} руб.")
        if hasattr(entity, "kind"):
            print(f"Вид жилья: {entity.kind()}")

    def _search(self) -> None:
        period = read_period()
        count = ask("Число гостей", int)
        city = ask("Город (пусто — любой)") or None
        objects = self.system.find_available(period, count, city)
        for housing in objects:
            print(f"{housing.id}: {housing.title}, {housing.address.city}, "
                  f"{housing.kind()}, {housing.price_per_night:.2f} руб./ночь")
        print(f"Найдено: {len(objects)}")

    def _file(self, save: bool) -> None:
        format_name = ask("Формат json/xml").lower()
        storages: dict[str, DataStorage] = {"json": JsonStorage(), "xml": XmlStorage()}
        if format_name not in storages:
            raise ValidationError("Поддерживаются форматы json и xml.")
        path = Path(ask("Путь", current=f"data/bookings.{format_name}"))
        storage = storages[format_name]
        if save:
            if path.exists() and ask("Перезаписать файл? да/нет") != "да":
                return
            storage.save(self.system, path)
            print(f"Данные записаны: {path}")
        elif self._confirm_replace():
            self.system = storage.load(path)
            print("Файл загружен; все связи восстановлены.")

    def _confirm_replace(self) -> bool:
        if not any(self.system.list(name) for name in self.system.COLLECTIONS):
            return True
        return ask("Заменить текущие данные? Несохранённое исчезнет. да/нет") == "да"
