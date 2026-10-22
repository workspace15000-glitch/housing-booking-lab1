"""Небольшие формы ввода объектов для консольного меню."""

from datetime import date
from decimal import Decimal
from typing import Any, Callable
from uuid import uuid4

from .exceptions import ValidationError
from .models import (
    Address, Amenity, Apartment, Booking, BookingStatus, DateRange, Guest,
    Host, House, HousingRules, Review, Room,
)
from .service import BookingSystem, Entity


def ask(label: str, convert: Callable[[str], Any] = str,
        current: Any = None) -> Any:
    """Пустой ответ при редактировании сохраняет текущее значение."""
    suffix = f" [{current}]" if current is not None else ""
    answer = input(f"{label}{suffix}: ").strip()
    return current if not answer and current is not None else convert(answer)


def boolean(text: str) -> bool:
    if text.lower() in ("да", "yes", "1", "true"):
        return True
    if text.lower() in ("нет", "no", "0", "false"):
        return False
    raise ValidationError("Введите да или нет.")


def read_period(current: DateRange | None = None) -> DateRange:
    return DateRange(
        check_in=ask("Заезд ГГГГ-ММ-ДД", date.fromisoformat,
                     current.check_in if current else None),
        check_out=ask("Выезд ГГГГ-ММ-ДД", date.fromisoformat,
                      current.check_out if current else None),
    )


class EntityForm:
    """Собирает поля; модели и сервис проверяют введённые значения."""

    def __init__(self, system: BookingSystem) -> None:
        self.system = system

    def read(self, collection: str, original: Entity | None = None) -> Entity:
        def value(label: str, field: str,
                  convert: Callable[[str], Any] = str) -> Any:
            return ask(label, convert, getattr(original, field, None))

        entity_id = original.id if original else ask("ID", current=uuid4().hex[:8])
        if collection in ("hosts", "guests"):
            cls = Host if collection == "hosts" else Guest
            return cls(id=entity_id, name=value("Имя", "name"),
                       email=value("Email", "email"))
        if collection == "amenities":
            return Amenity(id=entity_id, name=value("Название", "name"))
        if collection == "reviews":
            return Review(
                id=entity_id, booking_id=value("ID брони", "booking_id"),
                rating=value("Оценка 1–5", "rating", int),
                comment=value("Отзыв", "comment"),
            )
        if collection == "bookings":
            guest_id = value("ID гостя", "guest_id")
            housing_id = value("ID жилья", "accommodation_id")
            housing = self.system.get("accommodations", housing_id)
            return Booking(
                id=entity_id, guest_id=guest_id, accommodation_id=housing_id,
                period=read_period(original.period if original else None),
                guest_count=value("Число гостей", "guest_count", int),
                nightly_price=(original.nightly_price if original
                               else housing.price_per_night),
                status=(ask("Статус confirmed/cancelled", BookingStatus,
                            original.status) if original
                        else BookingStatus.CONFIRMED),
            )
        return self._housing(entity_id, original)

    def _housing(self, entity_id: str, original: Entity | None) -> Entity:
        classes = {"apartment": Apartment, "house": House, "room": Room}
        cls = type(original) if original else classes.get(
            ask("Вид: apartment / house / room")
        )
        if cls is None:
            raise ValidationError("Неизвестный вид жилья.")

        def value(label: str, field: str,
                  convert: Callable[[str], Any] = str) -> Any:
            return ask(label, convert, getattr(original, field, None))

        old_address = original.address if original else None
        address = Address(**{
            key: ask(label, current=getattr(old_address, key, None))
            for key, label in (("city", "Город"), ("street", "Улица"),
                               ("building", "Дом"))
        })
        old_rules = original.rules if original else HousingRules()
        amenities = ",".join(original.amenity_ids) if original else ""
        common = dict(
            id=entity_id, host_id=value("ID хозяина", "host_id"),
            title=value("Название", "title"), address=address,
            price_per_night=value("Цена за ночь, руб.", "price_per_night", Decimal),
            capacity=value("Вместимость", "capacity", int),
            amenity_ids=tuple(part.strip() for part in ask(
                "ID удобств через запятую (− очистить)", current=amenities
            ).split(",") if part.strip() and part.strip() != "−"),
            rules=HousingRules(
                smoking_allowed=ask("Курение да/нет", boolean,
                                    old_rules.smoking_allowed),
                pets_allowed=ask("Животные да/нет", boolean,
                                 old_rules.pets_allowed),
            ),
        )
        if cls is Apartment:
            common.update(rooms=value("Комнат", "rooms", int),
                          floor=value("Этаж", "floor", int))
        elif cls is House:
            common.update(floors=value("Этажей", "floors", int))
        else:
            common.update(shared_bathroom=ask(
                "Общая ванная да/нет", boolean,
                original.shared_bathroom if original else False,
            ))
        return cls(**common)
