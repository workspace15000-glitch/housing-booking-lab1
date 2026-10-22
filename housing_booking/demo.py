"""Воспроизводимый пример без пользовательского ввода."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from .exceptions import ConflictError
from .models import (
    Address, Amenity, Apartment, DateRange, Guest, Host, House, HousingRules,
    Review, Room,
)
from .service import BookingSystem
from .storage import JsonStorage, XmlStorage


def create_demo() -> BookingSystem:
    system = BookingSystem()
    system.add(Host(id="h1", name="Алексей", email="host@example.com"))
    system.add(Guest(id="g1", name="Мария", email="guest@example.com"))
    system.add(Amenity(id="wifi", name="Wi-Fi"))
    system.add(Amenity(id="parking", name="Парковка"))
    system.add(Apartment(
        id="a1", host_id="h1", title="Квартира в центре",
        address=Address(city="Москва", street="Учебная", building="1"),
        price_per_night=Decimal("3500.00"), capacity=3, rooms=2, floor=4,
        amenity_ids=("wifi",),
    ))
    system.add(House(
        id="h2", host_id="h1", title="Загородный дом",
        address=Address(city="Тула", street="Демонстрационная", building="2"),
        price_per_night=Decimal("6000.00"), capacity=6, floors=2,
        amenity_ids=("wifi", "parking"), rules=HousingRules(pets_allowed=True),
    ))
    system.add(Room(
        id="r1", host_id="h1", title="Комната для одного",
        address=Address(city="Москва", street="Учебная", building="3"),
        price_per_night=Decimal("1500.00"), capacity=1,
        shared_bathroom=True,
    ))
    system.create_booking("g1", "a1", DateRange(
        check_in=date(2026, 11, 1), check_out=date(2026, 11, 4)
    ), 2, booking_id="b1")
    system.create_booking("g1", "h2", DateRange(
        check_in=date(2026, 10, 1), check_out=date(2026, 10, 3)
    ), 2, booking_id="b2")
    system.add(Review(id="rev1", booking_id="b2", rating=5,
                      comment="Удобный дом, есть парковка."))
    system.create_booking("g1", "r1", DateRange(
        check_in=date(2026, 11, 8), check_out=date(2026, 11, 9)
    ), 1, booking_id="b3")
    system.cancel_booking("b3")
    return system


def run_demo(output_dir: str | Path = "data") -> None:
    system = create_demo()
    booking = system.get("bookings", "b1")
    print(f"Создана бронь b1: 3 ночи, {booking.total_price:.2f} руб.")
    system.update("accommodations", "a1", price_per_night=Decimal("4000.00"))
    print(f"Новый тариф: 4000.00; стоимость старой брони: {booking.total_price:.2f}")
    try:
        system.create_booking("g1", "a1", DateRange(
            check_in=date(2026, 11, 2), check_out=date(2026, 11, 5)
        ), 1)
    except ConflictError as error:
        print(f"Пересечение дат обработано: {error}")
    for suffix, storage in (("json", JsonStorage()), ("xml", XmlStorage())):
        path = Path(output_dir) / f"bookings.{suffix}"
        storage.save(system, path)
        restored = storage.load(path)
        print(f"{suffix.upper()}: сохранено и восстановлено "
              f"{len(restored.list('accommodations'))} объекта жилья, "
              f"{len(restored.list('bookings'))} брони, "
              f"{len(restored.list('reviews'))} отзыв.")
