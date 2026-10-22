from datetime import date


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Поле «{field}» не должно быть пустым")
    return value.strip()


def _positive(value: int, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"Поле «{field}» должно быть положительным целым числом")
    return value


class Person:
    def __init__(self, id: str, name: str, phone: str) -> None:
        self.id = _text(id, "ID")
        self.name = _text(name, "Имя")
        self.phone = _text(phone, "Телефон")

    def role(self) -> str:
        return "person"

    def __str__(self) -> str:
        return f"{self.role()}: {self.name} ({self.id})"


class Guest(Person):
    def role(self) -> str:
        return "guest"


class Host(Person):
    def role(self) -> str:
        return "host"


class Address:
    def __init__(self, city: str, street: str, building: str) -> None:
        self.city = _text(city, "Город")
        self.street = _text(street, "Улица")
        self.building = _text(building, "Дом")

    def __str__(self) -> str:
        return f"{self.city}, {self.street}, {self.building}"


class Amenity:
    def __init__(self, name: str) -> None:
        self.name = _text(name, "Удобство")

    def __str__(self) -> str:
        return self.name


class Rules:
    def __init__(self, pets_allowed: bool = False, smoking_allowed: bool = False) -> None:
        if type(pets_allowed) is not bool or type(smoking_allowed) is not bool:
            raise ValueError("Правила должны содержать значения True или False")
        self.pets_allowed = pets_allowed
        self.smoking_allowed = smoking_allowed


class Accommodation:
    def __init__(
        self, id: str, title: str, host_id: str, address: Address,
        price: int, capacity: int, amenities: list[Amenity] | None = None,
        rules: Rules | None = None,
    ) -> None:
        self.id = _text(id, "ID жилья")
        self.title = _text(title, "Название")
        self.host_id = _text(host_id, "ID хозяина")
        if not isinstance(address, Address):
            raise ValueError("Нужен объект Address")
        self.address = address
        # Цена за одну ночь в целых рублях.
        self.price = _positive(price, "Цена")
        self.capacity = _positive(capacity, "Вместимость")
        if amenities is None:
            amenities = []
        if not isinstance(amenities, list) or not all(
            isinstance(item, Amenity) for item in amenities
        ):
            raise ValueError("Удобства должны быть списком объектов Amenity")
        self.amenities = list(amenities)
        if rules is None:
            rules = Rules()
        if not isinstance(rules, Rules):
            raise ValueError("Нужен объект Rules")
        self.rules = rules

    def kind(self) -> str:
        return "housing"

    def __str__(self) -> str:
        return f"{self.id}: {self.title}, {self.price} руб./ночь"


class Apartment(Accommodation):
    def __init__(self, rooms: int = 1, **kwargs) -> None:
        super().__init__(**kwargs)
        self.rooms = _positive(rooms, "Количество комнат")

    def kind(self) -> str:
        return "apartment"


class House(Accommodation):
    def __init__(self, floors: int = 1, **kwargs) -> None:
        super().__init__(**kwargs)
        self.floors = _positive(floors, "Количество этажей")

    def kind(self) -> str:
        return "house"


class Room(Accommodation):
    def __init__(self, shared_bathroom: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        if type(shared_bathroom) is not bool:
            raise ValueError("Общий санузел: укажите True или False")
        self.shared_bathroom = shared_bathroom

    def kind(self) -> str:
        return "room"


class BookingPeriod:
    def __init__(self, check_in: str, check_out: str) -> None:
        try:
            self.check_in = date.fromisoformat(_text(check_in, "Дата заезда"))
            self.check_out = date.fromisoformat(_text(check_out, "Дата выезда"))
        except ValueError:
            raise ValueError("Даты должны иметь формат ГГГГ-ММ-ДД") from None
        if self.check_out <= self.check_in:
            raise ValueError("Дата выезда должна быть позже даты заезда")

    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def overlaps(self, other: "BookingPeriod") -> bool:
        # В день выезда может заехать следующий гость.
        return self.check_in < other.check_out and other.check_in < self.check_out

    def __str__(self) -> str:
        return f"{self.check_in} — {self.check_out}"


class Booking:
    def __init__(
        self, id: str, guest_id: str, accommodation_id: str,
        period: BookingPeriod, guest_count: int, price: int, status: str = "active",
    ) -> None:
        self.id = _text(id, "ID бронирования")
        self.guest_id = _text(guest_id, "ID гостя")
        self.accommodation_id = _text(accommodation_id, "ID жилья")
        if not isinstance(period, BookingPeriod):
            raise ValueError("Нужен объект BookingPeriod")
        self.period = period
        self.guest_count = _positive(guest_count, "Количество гостей")
        self.price = _positive(price, "Цена")
        if status not in ("active", "cancelled"):
            raise ValueError("Неизвестный статус бронирования")
        self.status = status

    def total_price(self) -> int:
        return self.period.nights() * self.price

    def cancel(self) -> None:
        self.status = "cancelled"
