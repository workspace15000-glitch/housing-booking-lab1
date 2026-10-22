"""Собственные исключения предметной области."""


class BookingError(Exception):
    """Базовая ошибка системы бронирования."""


class ValidationError(BookingError):
    """Некорректные значения полей."""


class NotFoundError(BookingError):
    """Объект с указанным идентификатором не найден."""


class ConflictError(BookingError):
    """Операция нарушает связи или правила бронирования."""


class StorageError(BookingError):
    """Не удалось прочитать или записать файл данных."""
