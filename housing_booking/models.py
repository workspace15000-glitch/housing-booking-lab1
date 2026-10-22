"""Неизменяемые объекты предметной области бронирования жилья.

Денежные значения задаются Decimal с точностью не более двух знаков после
запятой. Модель не округляет цены и не преобразует числа с плавающей точкой.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from .exceptions import ValidationError


def _validate_text(value: str, label: str, max_length: int = 200) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label}: требуется непустая строка.")
    if len(value) > max_length:
        raise ValidationError(f"{label}: допускается не более {max_length} символов.")
    # Один набор допустимых символов обеспечивает сохранение и в JSON, и в XML 1.0.
    if any(not (character in "\t\n\r" or "\x20" <= character <= "\ud7ff"
                or "\ue000" <= character <= "\ufffd"
                or "\U00010000" <= character <= "\U0010ffff") for character in value):
        raise ValidationError(f"{label}: символ недопустим в XML 1.0.")


def _validate_integer(value: int, label: str, minimum: int | None = None) -> None:
    # bool является подклассом int, но не подходит для количества или этажа.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"{label}: требуется целое число.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label}: значение должно быть не меньше {minimum}.")


def _validate_boolean(value: bool, label: str) -> None:
    if not isinstance(value, bool):
        raise ValidationError(f"{label}: требуется логическое значение.")


def _validate_money(value: Decimal, label: str) -> None:
    if not isinstance(value, Decimal):
        raise ValidationError(f"{label}: используйте Decimal.")
    if not value.is_finite() or value <= 0:
        raise ValidationError(f"{label}: требуется положительная конечная сумма.")
    if value.as_tuple().exponent < -2:
        raise ValidationError(f"{label}: допускается не более двух знаков после запятой.")


class BookingStatus(str, Enum):
    """Состояние бронирования."""

    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, kw_only=True)
class Address:
    """Адрес объекта размещения."""

    city: str
    street: str
    building: str

    def __post_init__(self) -> None:
        _validate_text(self.city, "Город")
        _validate_text(self.street, "Улица")
        _validate_text(self.building, "Номер дома", 50)


@dataclass(frozen=True, kw_only=True)
class Person(ABC):
    """Общий абстрактный класс участников бронирования."""

    id: str
    name: str
    email: str

    def __post_init__(self) -> None:
        _validate_text(self.id, "Идентификатор участника", 100)
        _validate_text(self.name, "Имя")
        _validate_text(self.email, "Электронная почта", 254)
        parts = self.email.split("@")
        if len(parts) != 2 or not all(parts) or any(c.isspace() for c in self.email):
            raise ValidationError("Электронная почта: ожидается адрес вида имя@домен.")

    @abstractmethod
    def role(self) -> str:
        """Вернуть роль участника в системе."""


@dataclass(frozen=True, kw_only=True)
class Guest(Person):
    """Гость, который бронирует жильё."""

    def role(self) -> str:
        return "guest"


@dataclass(frozen=True, kw_only=True)
class Host(Person):
    """Хозяин, который размещает предложения жилья."""

    def role(self) -> str:
        return "host"


@dataclass(frozen=True, kw_only=True)
class Amenity:
    """Удобство, например Wi-Fi или парковка."""

    id: str
    name: str

    def __post_init__(self) -> None:
        _validate_text(self.id, "Идентификатор удобства", 100)
        _validate_text(self.name, "Название удобства")


@dataclass(frozen=True, kw_only=True)
class HousingRules:
    """Правила проживания в объекте размещения."""

    smoking_allowed: bool = False
    pets_allowed: bool = False

    def __post_init__(self) -> None:
        _validate_boolean(self.smoking_allowed, "Разрешение курения")
        _validate_boolean(self.pets_allowed, "Разрешение проживания с животными")


@dataclass(frozen=True, kw_only=True)
class Accommodation(ABC):
    """Общие поля и поведение всех видов жилья."""

    id: str
    host_id: str
    title: str
    address: Address
    price_per_night: Decimal
    capacity: int
    amenity_ids: tuple[str, ...] = ()
    rules: HousingRules = field(default_factory=HousingRules)

    def __post_init__(self) -> None:
        _validate_text(self.id, "Идентификатор жилья", 100)
        _validate_text(self.host_id, "Идентификатор хозяина", 100)
        _validate_text(self.title, "Название жилья")
        if not isinstance(self.address, Address):
            raise ValidationError("Адрес: требуется объект Address.")
        _validate_money(self.price_per_night, "Цена за ночь")
        _validate_integer(self.capacity, "Вместимость", 1)
        if not isinstance(self.amenity_ids, tuple):
            raise ValidationError("Удобства: требуется кортеж идентификаторов.")
        for amenity_id in self.amenity_ids:
            _validate_text(amenity_id, "Идентификатор удобства", 100)
        if len(set(self.amenity_ids)) != len(self.amenity_ids):
            raise ValidationError("Удобства: идентификаторы не должны повторяться.")
        if not isinstance(self.rules, HousingRules):
            raise ValidationError("Правила проживания: требуется объект HousingRules.")

    @abstractmethod
    def kind(self) -> str:
        """Вернуть вид жилья для общего интерфейса работы с объектами."""


@dataclass(frozen=True, kw_only=True)
class Apartment(Accommodation):
    """Квартира с количеством комнат и номером этажа."""

    rooms: int = 1
    floor: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_integer(self.rooms, "Количество комнат", 1)
        _validate_integer(self.floor, "Этаж")

    def kind(self) -> str:
        return "apartment"


@dataclass(frozen=True, kw_only=True)
class House(Accommodation):
    """Отдельный дом с указанным количеством этажей."""

    floors: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_integer(self.floors, "Количество этажей", 1)

    def kind(self) -> str:
        return "house"


@dataclass(frozen=True, kw_only=True)
class Room(Accommodation):
    """Комната с отдельной или общей ванной."""

    shared_bathroom: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        _validate_boolean(self.shared_bathroom, "Общая ванная")

    def kind(self) -> str:
        return "room"


@dataclass(frozen=True, kw_only=True)
class DateRange:
    """Период проживания: дата выезда не включается в занятые даты."""

    check_in: date
    check_out: date

    def __post_init__(self) -> None:
        # datetime не принимается, хотя он наследует date.
        if type(self.check_in) is not date or type(self.check_out) is not date:
            raise ValidationError("Период проживания: требуются даты без времени.")
        if self.check_out <= self.check_in:
            raise ValidationError("Дата выезда должна быть позже даты заезда.")

    @property
    def nights(self) -> int:
        """Количество оплачиваемых ночей."""
        return (self.check_out - self.check_in).days

    def overlaps(self, other: DateRange) -> bool:
        """Проверить пересечение; выезд и следующий заезд в один день допустимы."""
        if not isinstance(other, DateRange):
            raise ValidationError("Для сравнения периодов требуется объект DateRange.")
        return self.check_in < other.check_out and other.check_in < self.check_out


@dataclass(frozen=True, kw_only=True)
class Booking:
    """Бронирование, сохраняющее цену за ночь на момент оформления."""

    id: str
    guest_id: str
    accommodation_id: str
    period: DateRange
    guest_count: int
    nightly_price: Decimal
    status: BookingStatus = BookingStatus.CONFIRMED

    def __post_init__(self) -> None:
        _validate_text(self.id, "Идентификатор бронирования", 100)
        _validate_text(self.guest_id, "Идентификатор гостя", 100)
        _validate_text(self.accommodation_id, "Идентификатор жилья", 100)
        if not isinstance(self.period, DateRange):
            raise ValidationError("Период проживания: требуется объект DateRange.")
        _validate_integer(self.guest_count, "Количество гостей", 1)
        _validate_money(self.nightly_price, "Цена за ночь в бронировании")
        if not isinstance(self.status, BookingStatus):
            raise ValidationError("Статус: требуется значение BookingStatus.")

    @property
    def total_price(self) -> Decimal:
        """Стоимость проживания по сохранённой цене."""
        return self.nightly_price * self.period.nights


@dataclass(frozen=True, kw_only=True)
class Review:
    """Отзыв по подтверждённому бронированию с оценкой от 1 до 5."""

    id: str
    booking_id: str
    rating: int
    comment: str

    def __post_init__(self) -> None:
        _validate_text(self.id, "Идентификатор отзыва", 100)
        _validate_text(self.booking_id, "Идентификатор бронирования", 100)
        _validate_integer(self.rating, "Оценка", 1)
        if self.rating > 5:
            raise ValidationError("Оценка должна быть от 1 до 5.")
        _validate_text(self.comment, "Текст отзыва", 2000)
