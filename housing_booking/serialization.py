"""Общая структура данных для JSON и XML."""

from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from . import models
from .exceptions import StorageError
from .service import BookingSystem


MODEL_TYPES = {
    cls.__name__: cls
    for cls in (
        models.Host, models.Guest, models.Amenity, models.Address,
        models.HousingRules, models.Apartment, models.House, models.Room,
        models.DateRange, models.Booking, models.Review,
    )
}


def encode(value: Any) -> Any:
    """Перевести объект в словари, списки и простые значения."""
    if is_dataclass(value):
        return {
            "type": type(value).__name__,
            **{field.name: encode(getattr(value, field.name))
               for field in fields(value)},
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, tuple):
        return [encode(item) for item in value]
    return value


def decode(record: Any) -> Any:
    """Восстановить только известные классы, не выполняя код из файла."""
    if not isinstance(record, dict):
        raise StorageError("Запись объекта должна быть словарём.")
    model_type = record.get("type")
    if not isinstance(model_type, str) or model_type not in MODEL_TYPES:
        raise StorageError("Неизвестный тип объекта.")
    cls = MODEL_TYPES[model_type]
    expected = {field.name for field in fields(cls)} | {"type"}
    if set(record) != expected:
        raise StorageError(f"Неверный набор полей объекта {model_type}.")
    values = {key: value for key, value in record.items() if key != "type"}
    for key, value in values.items():
        if key in ("address", "rules", "period"):
            values[key] = decode(value)
        elif key in ("price_per_night", "nightly_price"):
            if not isinstance(value, str):
                raise StorageError("Денежные значения должны быть строками.")
            values[key] = Decimal(value)
        elif key in ("check_in", "check_out"):
            values[key] = date.fromisoformat(value)
        elif key == "status":
            values[key] = models.BookingStatus(value)
        elif key == "amenity_ids":
            if not isinstance(value, list):
                raise StorageError("Список удобств должен быть массивом.")
            values[key] = tuple(value)
    return cls(**values)


def snapshot(system: BookingSystem) -> dict[str, Any]:
    """Сохранить все коллекции, включая связи и отменённые брони."""
    return {
        "schema_version": 1,
        **{name: [encode(item) for item in system.list(name)]
           for name in system.COLLECTIONS},
    }


def restore(document: Any) -> BookingSystem:
    """Проверить новый экземпляр до замены текущего в интерфейсе."""
    expected = {"schema_version", *BookingSystem.COLLECTIONS}
    if not isinstance(document, dict) or set(document) != expected:
        raise StorageError("Некорректная структура файла.")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise StorageError("Поддерживается только версия формата 1.")
    system = BookingSystem()
    for name in system.COLLECTIONS:
        records = document[name]
        if not isinstance(records, list):
            raise StorageError(f"Коллекция {name} должна быть массивом.")
        for record in records:
            entity = decode(record)
            # add сам выбирает коллекцию; проверяем также её имя в файле.
            system.add(entity)
            if entity not in system.list(name):
                raise StorageError(f"Объект помещён в неверную коллекцию {name}.")
    return system
