from exceptions import BookingError
from models import Accommodation, Booking, BookingPeriod, Guest, Host


class BookingSystem:
    def __init__(self) -> None:
        self.data = {"hosts": {}, "guests": {}, "housing": {}, "bookings": {}}

    def _collection(self, collection: str) -> dict:
        if collection not in self.data:
            raise BookingError("Неизвестный раздел")
        return self.data[collection]

    def _check(self, collection: str, obj: object, exclude_id: str = "") -> None:
        types = {"hosts": Host, "guests": Guest,
                 "housing": Accommodation, "bookings": Booking}
        if not isinstance(obj, types[collection]):
            raise BookingError("Объект не подходит для этого раздела")

        if collection == "housing":
            self.get("hosts", obj.host_id)
            for booking in self.get_all("bookings"):
                if (booking.accommodation_id == obj.id and
                        booking.status == "active" and
                        booking.guest_count > obj.capacity):
                    raise BookingError("В жилье уже есть бронь с большим числом гостей")

        if collection == "bookings":
            self.get("guests", obj.guest_id)
            housing = self.get("housing", obj.accommodation_id)
            if obj.status == "active" and obj.guest_count > housing.capacity:
                raise BookingError("Число гостей превышает вместимость жилья")
            if obj.status == "active":
                for booking in self.get_all("bookings"):
                    if (booking.id != exclude_id and
                            booking.accommodation_id == obj.accommodation_id and
                            booking.status == "active" and
                            booking.period.overlaps(obj.period)):
                        raise BookingError("Жильё уже занято на эти даты")

    def add(self, collection: str, obj: object) -> None:
        records = self._collection(collection)
        self._check(collection, obj)
        if obj.id in records:
            raise BookingError("Объект с таким номером уже существует")
        records[obj.id] = obj

    def get(self, collection: str, record_id: str) -> object:
        records = self._collection(collection)
        if record_id not in records:
            raise BookingError("Объект с таким номером не найден")
        return records[record_id]

    def get_all(self, collection: str) -> list:
        return list(self._collection(collection).values())

    def update(self, collection: str, record_id: str, replacement: object) -> None:
        old = self.get(collection, record_id)
        if type(replacement) is not type(old):
            raise BookingError("При изменении нельзя менять тип объекта")
        if replacement.id != record_id:
            raise BookingError("При изменении нельзя менять номер объекта")
        self._check(collection, replacement, exclude_id=record_id)
        self.data[collection][record_id] = replacement

    def delete(self, collection: str, record_id: str) -> None:
        self.get(collection, record_id)
        if collection == "hosts":
            for housing in self.get_all("housing"):
                if housing.host_id == record_id:
                    raise BookingError("Нельзя удалить хозяина, у которого есть жильё")
        if collection == "guests":
            for booking in self.get_all("bookings"):
                if booking.guest_id == record_id:
                    raise BookingError("Гость используется в бронировании")
        if collection == "housing":
            for booking in self.get_all("bookings"):
                if booking.accommodation_id == record_id:
                    raise BookingError("Жильё используется в бронировании")
        del self.data[collection][record_id]

    def book(self, booking_id: str, guest_id: str, housing_id: str,
             period: BookingPeriod, guest_count: int) -> Booking:
        housing = self.get("housing", housing_id)
        booking = Booking(booking_id, guest_id, housing_id, period,
                          guest_count, housing.price)
        self.add("bookings", booking)
        return booking

    def cancel_booking(self, booking_id: str) -> None:
        booking = self.get("bookings", booking_id)
        booking.cancel()

    def available(self, period: BookingPeriod, guest_count: int,
                  city: str = "") -> list:
        if type(guest_count) is not int or guest_count < 1:
            raise BookingError("Число гостей должно быть положительным")
        result = []
        for housing in self.get_all("housing"):
            if housing.capacity < guest_count:
                continue
            if city and housing.address.city.lower() != city.strip().lower():
                continue
            occupied = False
            for booking in self.get_all("bookings"):
                if (booking.accommodation_id == housing.id and
                        booking.status == "active" and
                        booking.period.overlaps(period)):
                    occupied = True
                    break
            if not occupied:
                result.append(housing)
        return result
