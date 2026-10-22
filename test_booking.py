"""Проверки правил бронирования, целостности данных и файловых форматов."""

import copy
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from housing_booking.exceptions import ConflictError, NotFoundError, StorageError, ValidationError
from housing_booking.models import (
    Accommodation, Address, Amenity, Apartment, Booking, BookingStatus, DateRange,
    Guest, Host, House, HousingRules, Person, Review, Room,
)
from housing_booking.serialization import snapshot
from housing_booking.service import BookingSystem
from housing_booking.storage import JsonStorage, XmlStorage


def period(start: int = 1, end: int = 3) -> DateRange:
    return DateRange(check_in=date(2026, 5, start), check_out=date(2026, 5, end))


def populated_system() -> BookingSystem:
    """Все виды жилья и коллекции, включая отменённую бронь и отзыв."""
    system = BookingSystem()
    system.add(Host(id="h1", name="Анна", email="host@example.com"))
    system.add(Guest(id="g1", name="Иван", email="guest@example.com"))
    system.add(Amenity(id="wifi", name="Wi-Fi"))
    common = dict(host_id="h1", address=Address(city="Москва", street="Лесная", building="1"),
                  price_per_night=Decimal("2500.50"), amenity_ids=("wifi",))
    system.add(Apartment(id="a1", title="Квартира", capacity=2, rooms=2, floor=3,
                         rules=HousingRules(pets_allowed=True), **common))
    system.add(House(id="a2", title="Дом", capacity=4, floors=2, **common))
    system.add(Room(id="a3", title="Комната", capacity=1, shared_bathroom=True, **common))
    system.create_booking("g1", "a1", period(), 2, "b1")
    system.create_booking("g1", "a2", period(), 1, "b2")
    system.cancel_booking("b2")
    system.add(Review(id="r1", booking_id="b1", rating=5, comment="Уютная квартира"))
    return system


class ModelTests(unittest.TestCase):
    def test_abstract_bases_polymorphism_and_immutability(self):
        system = populated_system()
        self.assertEqual([item.kind() for item in system.list("accommodations")],
                         ["apartment", "house", "room"])
        self.assertEqual(system.get("hosts", "h1").role(), "host")
        self.assertEqual(system.get("guests", "g1").role(), "guest")
        with self.assertRaises(TypeError):
            Person(id="p", name="Имя", email="p@example.com")
        with self.assertRaises(TypeError):
            Accommodation()
        with self.assertRaises(FrozenInstanceError):
            system.get("accommodations", "a1").title = "Изменено"

    def test_invalid_model_fields(self):
        apartment = populated_system().get("accommodations", "a1")
        invalid = [{"capacity": True}, {"capacity": 0}, {"rooms": 0}, {"floor": False},
                   {"title": " "}, {"price_per_night": 1.5},
                   *({"price_per_night": Decimal(value)}
                     for value in ("NaN", "Infinity", "0", "-1", "1.001")),
                   {"amenity_ids": ["wifi"]}, {"amenity_ids": ("wifi", "wifi")},
                   {"address": "Москва"}, {"rules": {}}]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                replace(apartment, **changes)
        constructors = [lambda: HousingRules(pets_allowed=1),
                        lambda: Host(id="h", name="Имя", email="не адрес"),
                        lambda: Address(city="Москва", street="Улица", building=1),
                        lambda: Amenity(id="wifi", name=""),
                        lambda: replace(populated_system().get("accommodations", "a2"), floors=0),
                        lambda: replace(populated_system().get("accommodations", "a3"), shared_bathroom=1),
                        lambda: Review(id="r", booking_id="b", rating=True, comment="Текст"),
                        lambda: Review(id="r", booking_id="b", rating=6, comment="Текст"),
                        lambda: replace(populated_system().get("bookings", "b1"), guest_count=True),
                        lambda: replace(populated_system().get("bookings", "b1"), status="confirmed")]
        for constructor in constructors:
            with self.assertRaises(ValidationError):
                constructor()

    def test_date_boundaries_and_validation(self):
        self.assertEqual(period().nights, 2)
        self.assertTrue(period().overlaps(period(2, 4)))
        self.assertFalse(period().overlaps(period(3, 4)))
        self.assertFalse(period(3, 4).overlaps(period()))
        for check_in, check_out in [(date(2026, 5, 3), date(2026, 5, 3)),
                                    (date(2026, 5, 4), date(2026, 5, 3)),
                                    (datetime(2026, 5, 1), date(2026, 5, 3))]:
            with self.assertRaises(ValidationError):
                DateRange(check_in=check_in, check_out=check_out)

    def test_total_price_uses_decimal(self):
        booking = populated_system().get("bookings", "b1")
        self.assertIsInstance(booking.total_price, Decimal)
        self.assertEqual(booking.total_price, Decimal("5001.00"))

    def test_text_rejects_non_xml_characters(self):
        for codepoint in (*range(9), 11, 12, *range(14, 32), 0xD800, 0xDFFF, 0xFFFE, 0xFFFF):
            with self.subTest(codepoint=hex(codepoint)), self.assertRaises(ValidationError):
                Host(id="h", name="A" + chr(codepoint) + "B", email="a@b")


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.system = populated_system()

    def test_crud_all_collections_and_dependency_order(self):
        updates = {"hosts": ("h1", {"name": "Ольга"}), "guests": ("g1", {"name": "Пётр"}),
                   "amenities": ("wifi", {"name": "Интернет"}),
                   "accommodations": ("a1", {"title": "Новая квартира"}),
                   "bookings": ("b1", {"guest_count": 1}), "reviews": ("r1", {"rating": 4})}
        for collection, (id, changes) in updates.items():
            original = self.system.get(collection, id)
            updated = self.system.update(collection, id, **changes)
            self.assertIn(updated, self.system.list(collection))
            self.assertEqual(self.system.get(collection, id), updated)
            self.assertNotEqual(original, updated)
        for collection in ("reviews", "bookings", "accommodations", "amenities", "guests", "hosts"):
            for entity in self.system.list(collection):
                self.system.delete(collection, entity.id)
            self.assertEqual(self.system.list(collection), ())

    def test_duplicate_missing_and_unsupported_objects(self):
        before = snapshot(self.system)
        with self.assertRaises(ConflictError):
            self.system.add(self.system.get("hosts", "h1"))
        with self.assertRaises(NotFoundError):
            self.system.get("hosts", "missing")
        for action in (lambda: self.system.list("unknown"), lambda: self.system.add("host"),
                       lambda: self.system.update("hosts", "h1", id="other"),
                       lambda: self.system.update("hosts", "h1", unknown="value")):
            with self.assertRaises(ValidationError):
                action()
        self.assertEqual(snapshot(self.system), before)

    def test_conflicting_and_adjacent_bookings(self):
        before = snapshot(self.system)
        with self.assertRaises(ConflictError):
            self.system.create_booking("g1", "a1", period(2, 4), 1, "overlap")
        self.assertEqual(snapshot(self.system), before)
        adjacent = self.system.create_booking("g1", "a1", period(3, 4), 1, "adjacent")
        self.assertEqual(adjacent.period, period(3, 4))
        before = snapshot(self.system)
        with self.assertRaises(ConflictError):
            self.system.update("bookings", "adjacent", period=period(2, 4))
        self.assertEqual(snapshot(self.system), before)

    def test_cancel_releases_dates_and_keeps_history(self):
        self.system.delete("reviews", "r1")
        cancelled = self.system.cancel_booking("b1")
        self.assertEqual(cancelled.status, BookingStatus.CANCELLED)
        self.assertIn(self.system.get("accommodations", "a1"), self.system.find_available(period()))
        self.system.create_booking("g1", "a1", period(), 1, "replacement")
        self.assertEqual(len(self.system.list("bookings")), 3)
        with self.assertRaises(ConflictError):
            self.system.update("bookings", "b1", status=BookingStatus.CONFIRMED)

    def test_booking_keeps_price_after_listing_change(self):
        original = self.system.get("bookings", "b1")
        self.system.update("accommodations", "a1", price_per_night=Decimal("9999.00"))
        self.assertEqual(self.system.get("bookings", "b1"), original)
        with self.assertRaises(ValidationError):
            self.system.update("bookings", "b1", nightly_price=Decimal("1.00"))
        moved = self.system.update("bookings", "b1", accommodation_id="a2")
        self.assertEqual(moved.nightly_price, self.system.get("accommodations", "a2").price_per_night)

    def test_failed_linked_changes_are_atomic(self):
        before = snapshot(self.system)
        actions = [lambda c=c, i=i: self.system.delete(c, i) for c, i in
                   [("hosts", "h1"), ("guests", "g1"), ("amenities", "wifi"),
                    ("accommodations", "a1"), ("bookings", "b1")]]
        actions += [lambda: self.system.update("accommodations", "a1", capacity=1),
                    lambda: self.system.update("accommodations", "a1", host_id="missing"),
                    lambda: self.system.update("accommodations", "a1", amenity_ids=("missing",)),
                    lambda: self.system.cancel_booking("b1")]
        for action in actions:
            with self.assertRaises(ConflictError):
                action()
            self.assertEqual(snapshot(self.system), before)

    def test_missing_references_capacity_and_review_constraints(self):
        before = snapshot(self.system)
        bad_objects = [replace(self.system.get("accommodations", "a1"), id="orphan", host_id="missing"),
                       replace(self.system.get("bookings", "b1"), id="orphan", guest_id="missing"),
                       Review(id="r2", booking_id="b1", rating=4, comment="Повтор"),
                       Review(id="r3", booking_id="b2", rating=4, comment="Отмена")]
        for entity in bad_objects:
            with self.assertRaises(ConflictError):
                self.system.add(entity)
            self.assertEqual(snapshot(self.system), before)
        with self.assertRaises(ConflictError):
            self.system.create_booking("g1", "a3", period(), 2, "too-many")
        self.assertEqual(snapshot(self.system), before)

    def test_search_filters_and_invalid_input(self):
        self.assertEqual([a.id for a in self.system.find_available(period(), 2, "мОСКВА")], ["a2"])
        self.assertEqual(self.system.find_available(period(), 1, "Казань"), ())
        for count in (True, 0, "2"):
            with self.assertRaises(ValidationError):
                self.system.find_available(period(), count)
        with self.assertRaises(ValidationError):
            self.system.find_available("2026-05-01")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.system = populated_system()
        self.temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "data"

    def assert_roundtrip(self, storage):
        storage.save(self.system, self.path)
        loaded = storage.load(self.path)
        self.assertEqual(snapshot(loaded), snapshot(self.system))
        for id, cls in (("a1", Apartment), ("a2", House), ("a3", Room)):
            item = loaded.get("accommodations", id)
            self.assertIs(type(item), cls)
            self.assertIsInstance(item.address, Address)
            self.assertIsInstance(item.rules, HousingRules)
            self.assertIsInstance(item.price_per_night, Decimal)
            self.assertIsInstance(item.amenity_ids, tuple)
        self.assertIs(type(loaded.get("bookings", "b1").period.check_in), date)
        self.assertIsInstance(loaded.get("bookings", "b1").nightly_price, Decimal)
        self.assertIs(loaded.get("bookings", "b2").status, BookingStatus.CANCELLED)
        self.assertTrue(loaded.get("accommodations", "a1").rules.pets_allowed)

    def test_json_roundtrip(self):
        self.assert_roundtrip(JsonStorage())

    def test_xml_roundtrip(self):
        self.assert_roundtrip(XmlStorage())

    def test_whitespace_text_roundtrip(self):
        self.system.update("hosts", "h1", name="Анна\t\r\nХозяин\rКвартира\nЖильё")
        for storage in (JsonStorage(), XmlStorage()):
            with self.subTest(format=type(storage).__name__):
                self.assert_roundtrip(storage)

    def test_missing_and_malformed_files(self):
        for storage in (JsonStorage(), XmlStorage()):
            with self.assertRaises(StorageError):
                storage.load(self.path / "missing")
            self.path.write_text("{broken <file", encoding="utf-8")
            with self.assertRaises(StorageError):
                storage.load(self.path)

    def test_invalid_documents_in_both_formats(self):
        valid = snapshot(self.system)
        variants = []
        for collection, key, value in [("bookings", "status", "unknown"),
                                       ("bookings", "guest_id", "missing"),
                                       ("accommodations", "type", "Unknown")]:
            document = copy.deepcopy(valid)
            document[collection][0][key] = value
            variants.append(document)
        document = copy.deepcopy(valid)
        document["hosts"].append(copy.deepcopy(document["hosts"][0]))
        variants.append(document)
        document = copy.deepcopy(valid)
        document["guests"] = document["hosts"]
        variants += [document, {**valid, "hosts": {}}, {**valid, "extra": []},
                     {**valid, "schema_version": True}, []]
        for storage in (JsonStorage(), XmlStorage()):
            for case, document in enumerate(variants):
                with self.subTest(format=type(storage).__name__, case=case):
                    self.path.write_text(storage.dumps(document), encoding="utf-8")
                    with self.assertRaises(StorageError):
                        storage.load(self.path)

    def test_duplicate_keys_are_rejected(self):
        for storage, text in [(JsonStorage(), '{"schema_version":1,"schema_version":1}'),
                              (XmlStorage(), '<booking_system kind="object"><x kind="int">1</x>'
                               '<x kind="int">2</x></booking_system>')]:
            self.path.write_text(text, encoding="utf-8")
            with self.assertRaises(StorageError):
                storage.load(self.path)

    def test_xml_rejects_wrong_root_and_node_types(self):
        for text in ['<wrong kind="object"/>', '<booking_system kind="unknown"/>',
                     '<booking_system kind="bool">yes</booking_system>',
                     '<booking_system kind="list"><wrong kind="str"/></booking_system>',
                     '<booking_system kind="object">extra text</booking_system>',
                     '<booking_system kind="object" extra="value"/>']:
            self.path.write_text(text, encoding="utf-8")
            with self.assertRaises(StorageError):
                XmlStorage().load(self.path)


if __name__ == "__main__":
    unittest.main()
