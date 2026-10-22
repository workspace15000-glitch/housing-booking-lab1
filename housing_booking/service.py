"""Операции над объектами и согласованность системы бронирования."""

from dataclasses import replace
from typing import TypeAlias
from uuid import uuid4

from .exceptions import ConflictError, NotFoundError, ValidationError
from .models import (
    Accommodation,
    Amenity,
    Booking,
    BookingStatus,
    DateRange,
    Guest,
    Host,
    Review,
)


Entity: TypeAlias = Host | Guest | Amenity | Accommodation | Booking | Review
State: TypeAlias = dict[str, dict[str, Entity]]
COLLECTIONS = (
    "hosts", "guests", "amenities", "accommodations", "bookings", "reviews"
)


class BookingSystem:
    """Хранит объекты в памяти и проверяет каждое изменение до сохранения.

    Возвращаемые объекты неизменяемы, а списки представлены кортежами.
    Поэтому изменить состояние в обход проверок через публичный API нельзя.
    """

    COLLECTIONS = COLLECTIONS

    def __init__(self) -> None:
        self._data: State = {name: {} for name in COLLECTIONS}

    def add(self, entity: Entity) -> None:
        """Добавляет объект, проверяя уникальность и предметные связи."""
        collection = self._collection_for(entity)
        if entity.id in self._data[collection]:
            raise ConflictError(
                f"В коллекции «{collection}» уже есть объект «{entity.id}»."
            )
        candidate = self._copy_state()
        candidate[collection][entity.id] = entity
        self._commit(candidate)

    def get(self, collection: str, id: str) -> Entity:
        """Возвращает один объект либо сообщает, что он не найден."""
        self._check_collection(collection)
        if not isinstance(id, str) or not id.strip():
            raise ValidationError("Идентификатор должен быть непустой строкой.")
        try:
            return self._data[collection][id]
        except KeyError as error:
            raise NotFoundError(
                f"В коллекции «{collection}» нет объекта «{id}»."
            ) from error

    def list(self, collection: str) -> tuple[Entity, ...]:
        """Возвращает снимок коллекции в порядке добавления объектов."""
        self._check_collection(collection)
        return tuple(self._data[collection].values())

    def update(self, collection: str, entity_id: str, **changes: object) -> Entity:
        """Создаёт изменённый объект и атомарно проверяет всё состояние."""
        original = self.get(collection, entity_id)
        if "id" in changes:
            raise ValidationError("Идентификатор объекта изменять нельзя.")
        if isinstance(original, Booking):
            if "nightly_price" in changes:
                raise ValidationError(
                    "Цена бронирования изменяется только при смене жилья."
                )
            if (
                original.status == BookingStatus.CANCELLED
                and "status" in changes
                and changes["status"] != BookingStatus.CANCELLED
            ):
                raise ConflictError(
                    "Отменённое бронирование нельзя подтвердить повторно."
                )
            accommodation_id = changes.get(
                "accommodation_id", original.accommodation_id
            )
            if accommodation_id != original.accommodation_id:
                accommodation = self.get("accommodations", accommodation_id)
                assert isinstance(accommodation, Accommodation)
                changes["nightly_price"] = accommodation.price_per_night
        try:
            updated = replace(original, **changes)
        except TypeError as error:
            raise ValidationError(
                f"Некорректные поля изменения: {error}"
            ) from error
        candidate = self._copy_state()
        candidate[collection][entity_id] = updated
        self._commit(candidate)
        return updated

    def delete(self, collection: str, id: str) -> None:
        """Удаляет объект, только если оставшиеся связи сохранятся."""
        self.get(collection, id)
        candidate = self._copy_state()
        del candidate[collection][id]
        self._commit(candidate)

    def create_booking(
        self,
        guest_id: str,
        accommodation_id: str,
        period: DateRange,
        guest_count: int,
        booking_id: str | None = None,
    ) -> Booking:
        """Бронирует жильё и фиксирует действовавшую стоимость ночи."""
        self.get("guests", guest_id)
        accommodation = self.get("accommodations", accommodation_id)
        assert isinstance(accommodation, Accommodation)
        booking = Booking(
            id=uuid4().hex if booking_id is None else booking_id,
            guest_id=guest_id,
            accommodation_id=accommodation_id,
            period=period,
            guest_count=guest_count,
            nightly_price=accommodation.price_per_night,
        )
        self.add(booking)
        return booking

    def cancel_booking(self, id: str) -> Booking:
        """Отменяет бронирование и освобождает его даты для поиска."""
        booking = self.update("bookings", id, status=BookingStatus.CANCELLED)
        assert isinstance(booking, Booking)
        return booking

    def find_available(
        self,
        period: DateRange,
        guest_count: int = 1,
        city: str | None = None,
    ) -> tuple[Accommodation, ...]:
        """Ищет свободное жильё по вместимости, периоду и городу."""
        if not isinstance(period, DateRange):
            raise ValidationError("Период должен быть объектом DateRange.")
        if (
            isinstance(guest_count, bool)
            or not isinstance(guest_count, int)
            or guest_count < 1
        ):
            raise ValidationError(
                "Число гостей должно быть положительным целым числом."
            )
        if city is not None and (not isinstance(city, str) or not city.strip()):
            raise ValidationError("Город должен быть непустой строкой.")
        result = []
        for accommodation in self._data["accommodations"].values():
            assert isinstance(accommodation, Accommodation)
            if accommodation.capacity < guest_count:
                continue
            if (
                city is not None
                and accommodation.address.city.casefold() != city.strip().casefold()
            ):
                continue
            occupied = any(
                isinstance(booking, Booking)
                and booking.status == BookingStatus.CONFIRMED
                and booking.accommodation_id == accommodation.id
                and booking.period.overlaps(period)
                for booking in self._data["bookings"].values()
            )
            if not occupied:
                result.append(accommodation)
        return tuple(result)

    @staticmethod
    def _collection_for(entity: Entity) -> str:
        for model, collection in (
            (Host, "hosts"),
            (Guest, "guests"),
            (Amenity, "amenities"),
            (Accommodation, "accommodations"),
            (Booking, "bookings"),
            (Review, "reviews"),
        ):
            if isinstance(entity, model):
                return collection
        raise ValidationError("Этот тип объекта не поддерживается системой.")

    @staticmethod
    def _check_collection(collection: str) -> None:
        if not isinstance(collection, str) or collection not in COLLECTIONS:
            raise ValidationError(f"Неизвестная коллекция «{collection}».")

    def _copy_state(self) -> State:
        return {
            collection: dict(items) for collection, items in self._data.items()
        }

    def _commit(self, candidate: State) -> None:
        self._validate_state(candidate)
        self._data = candidate

    @staticmethod
    def _require(state: State, collection: str, id: str, relation: str) -> Entity:
        try:
            return state[collection][id]
        except KeyError as error:
            raise ConflictError(
                f"{relation}: объект «{id}» отсутствует."
            ) from error

    @classmethod
    def _validate_state(cls, state: State) -> None:
        """Проверяет связи, вместимость, пересечения и уникальность отзывов."""
        for accommodation in state["accommodations"].values():
            assert isinstance(accommodation, Accommodation)
            cls._require(state, "hosts", accommodation.host_id, "Владелец жилья")
            for amenity_id in accommodation.amenity_ids:
                cls._require(state, "amenities", amenity_id, "Удобство жилья")

        confirmed = []
        for booking in state["bookings"].values():
            assert isinstance(booking, Booking)
            cls._require(state, "guests", booking.guest_id, "Гость бронирования")
            accommodation = cls._require(
                state,
                "accommodations",
                booking.accommodation_id,
                "Жильё бронирования",
            )
            assert isinstance(accommodation, Accommodation)
            if booking.status == BookingStatus.CONFIRMED:
                if booking.guest_count > accommodation.capacity:
                    raise ConflictError(
                        f"Бронирование «{booking.id}» превышает вместимость жилья."
                    )
                for other in confirmed:
                    if (
                        booking.accommodation_id == other.accommodation_id
                        and booking.period.overlaps(other.period)
                    ):
                        raise ConflictError(
                            f"Бронирования «{other.id}» и «{booking.id}» пересекаются."
                        )
                confirmed.append(booking)

        reviewed = set()
        for review in state["reviews"].values():
            assert isinstance(review, Review)
            booking = cls._require(
                state, "bookings", review.booking_id, "Бронирование отзыва"
            )
            assert isinstance(booking, Booking)
            if booking.status != BookingStatus.CONFIRMED:
                raise ConflictError(
                    "Отзыв может относиться только к подтверждённому бронированию."
                )
            if booking.id in reviewed:
                raise ConflictError(
                    "Для одного бронирования разрешён только один отзыв."
                )
            reviewed.add(booking.id)
