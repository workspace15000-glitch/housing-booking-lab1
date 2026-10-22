from xml.etree import ElementTree as ET

from booking_system import BookingSystem
from exceptions import BookingError
from models import (
    Accommodation, Address, Amenity, Apartment, Booking, BookingPeriod, Guest, Host,
    House, Room, Rules,
)
from storage import FileStorage


def ask(label: str, default=None) -> str:
    hint = f" [{default}]" if default is not None else ""
    answer = input(label + hint + ": ").strip()
    return str(default) if not answer and default is not None else answer


def yes_no(label: str, default: bool = False) -> bool:
    answer = ask(label + " (да/нет)", "да" if default else "нет").lower()
    if answer not in ("да", "нет"):
        raise ValueError("Введите да или нет")
    return answer == "да"


def read_period(old: BookingPeriod | None = None) -> BookingPeriod:
    start = ask("Заезд ГГГГ-ММ-ДД", old.check_in if old else None)
    end = ask("Выезд ГГГГ-ММ-ДД", old.check_out if old else None)
    return BookingPeriod(start, end)


def read_housing(old=None):
    kind = old.kind() if old else ask("Вид: apartment, house или room")
    classes = {"apartment": Apartment, "house": House, "room": Room}
    if kind not in classes:
        raise ValueError("Неизвестный вид жилья")
    address = old.address if old else None
    rules = old.rules if old else Rules()
    values = {
        "id": old.id if old else ask("ID жилья"),
        "title": ask("Название", old.title if old else None),
        "host_id": ask("ID хозяина", old.host_id if old else None),
        "address": Address(
            ask("Город", address.city if address else None),
            ask("Улица", address.street if address else None),
            ask("Дом", address.building if address else None),
        ),
        "price": int(ask("Цена за ночь, целые рубли", old.price if old else None)),
        "capacity": int(ask("Вместимость", old.capacity if old else None)),
    }
    previous = ", ".join(item.name for item in old.amenities) if old else ""
    names = ask("Удобства через запятую (− очистить)", previous)
    values["amenities"] = [Amenity(name.strip()) for name in names.split(",")
                           if name.strip() and name.strip() != "−"]
    values["rules"] = Rules(yes_no("Можно с животными", rules.pets_allowed),
                            yes_no("Можно курить", rules.smoking_allowed))
    if kind == "apartment":
        values["rooms"] = int(ask("Количество комнат", old.rooms if old else 1))
    elif kind == "house":
        values["floors"] = int(ask("Количество этажей", old.floors if old else 1))
    else:
        values["shared_bathroom"] = yes_no(
            "Общий санузел", old.shared_bathroom if old else False
        )
    return classes[kind](**values)


def read_record(system: BookingSystem, collection: str, old=None):
    if collection == "housing":
        return read_housing(old)
    record_id = old.id if old else ask("ID")
    if collection in ("guests", "hosts"):
        person_class = Guest if collection == "guests" else Host
        return person_class(record_id, ask("Имя", old.name if old else None),
                            ask("Телефон", old.phone if old else None))
    guest_id = ask("ID гостя", old.guest_id if old else None)
    housing_id = ask("ID жилья", old.accommodation_id if old else None)
    housing = system.get("housing", housing_id)
    period = read_period(old.period if old else None)
    count = int(ask("Число гостей", old.guest_count if old else None))
    price = old.price if old and old.accommodation_id == housing_id else housing.price
    return Booking(record_id, guest_id, housing_id, period, count, price,
                   old.status if old else "active")


def show_record(record) -> None:
    if isinstance(record, Booking):
        status = "действует" if record.status == "active" else "отменена"
        print(f"{record.id}: гость {record.guest_id}, жильё {record.accommodation_id}")
        print(f"  {record.period}; гостей: {record.guest_count}; "
              f"стоимость: {record.total_price()} руб.; {status}")
    elif isinstance(record, Accommodation):
        print(record)
        print(f"  {record.kind()}, {record.address}, мест: {record.capacity}")
        print(f"  Хозяин: {record.host_id}; удобства: "
              + ", ".join(str(item) for item in record.amenities))
        print(f"  Животные: {record.rules.pets_allowed}; "
              f"курение: {record.rules.smoking_allowed}")
        if isinstance(record, Apartment):
            print(f"  Комнат: {record.rooms}")
        elif isinstance(record, House):
            print(f"  Этажей: {record.floors}")
        elif isinstance(record, Room):
            print(f"  Общий санузел: {record.shared_bathroom}")
    else:
        print(record)
        print(f"  Телефон: {record.phone}")


def manage(system: BookingSystem, collection: str) -> None:
    print("1 Список | 2 Добавить | 3 Изменить | 4 Удалить")
    if collection == "bookings":
        print("5 Отменить бронь")
    action = ask("Действие")
    if action == "1":
        records = system.get_all(collection)
        for record in records:
            show_record(record)
        if not records:
            print("Записей пока нет")
    elif action == "2":
        system.add(collection, read_record(system, collection))
        print("Добавлено")
    elif action == "3":
        record_id = ask("ID записи")
        old = system.get(collection, record_id)
        print("Пустой ответ оставляет прежнее значение")
        replacement = read_record(system, collection, old)
        system.update(collection, record_id, replacement)
        print("Изменено")
    elif action == "4":
        record_id = ask("ID записи")
        if yes_no("Удалить запись"):
            system.delete(collection, record_id)
            print("Удалено")
    elif action == "5" and collection == "bookings":
        system.cancel_booking(ask("ID брони"))
        print("Бронь отменена")
    else:
        raise ValueError("Нет такого действия")


def add_example(system: BookingSystem) -> None:
    system.add("hosts", Host("h1", "Алексей", "000-00-01"))
    system.add("guests", Guest("g1", "Мария", "000-00-02"))
    system.add("housing", Apartment(
        id="a1", title="Квартира в центре", host_id="h1",
        address=Address("Москва", "Учебная", "1"), price=3000, capacity=3,
        rooms=2, amenities=[Amenity("Wi-Fi")], rules=Rules(pets_allowed=True),
    ))
    system.book("b1", "g1", "a1", BookingPeriod("2026-11-01", "2026-11-04"), 2)


def main() -> None:
    system = BookingSystem()
    storage = FileStorage()
    collections = {"1": "guests", "2": "hosts", "3": "housing", "4": "bookings"}
    while True:
        try:
            print("\n1 Гости | 2 Хозяева | 3 Жильё | 4 Бронирования")
            print("5 Поиск жилья | 6 Сохранить | 7 Загрузить | 8 Пример | 0 Выход")
            choice = ask("Выбор")
            if choice == "0":
                return
            if choice in collections:
                manage(system, collections[choice])
            elif choice == "5":
                period = read_period()
                count = int(ask("Число гостей"))
                city = ask("Город (пусто — любой)")
                found = system.available(period, count, city)
                for housing in found:
                    show_record(housing)
                print(f"Найдено: {len(found)}")
            elif choice in ("6", "7"):
                format_name = ask("Формат json или xml").lower()
                if format_name not in ("json", "xml"):
                    raise ValueError("Выберите json или xml")
                path = ask("Имя файла", f"bookings.{format_name}")
                if choice == "6":
                    if format_name == "json":
                        storage.save_json(system, path)
                    else:
                        storage.save_xml(system, path)
                    print("Файл сохранён")
                elif yes_no("Заменить текущие данные данными из файла"):
                    loaded = (storage.load_json(path) if format_name == "json"
                              else storage.load_xml(path))
                    system = loaded
                    print("Данные загружены")
            elif choice == "8":
                add_example(system)
                print("Пример добавлен: хозяин h1, гость g1, квартира a1, бронь b1")
            else:
                print("Нет такого пункта")
        except (BookingError, ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
            print(f"Ошибка: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nВыход. Данные сохраняются через пункт 6")
            return


if __name__ == "__main__":
    main()
