"""Чтение и запись файлов. Оба формата используют одинаковую модель."""

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from xml.etree import ElementTree as ET

from .exceptions import BookingError, StorageError
from .serialization import restore, snapshot
from .service import BookingSystem


class DataStorage(ABC):
    """Общий интерфейс хранилища и безопасная замена готового файла."""

    def save(self, system: BookingSystem, path: str | Path) -> None:
        target = Path(path)
        temporary: str | None = None
        try:
            text = self.dumps(snapshot(system))
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=target.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temporary = stream.name
                stream.write(text)
            os.replace(temporary, target)
        except (OSError, ValueError, TypeError) as error:
            raise StorageError(f"Не удалось сохранить файл: {error}") from error
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def load(self, path: str | Path) -> BookingSystem:
        try:
            return restore(self.loads(Path(path).read_text(encoding="utf-8")))
        except StorageError:
            raise
        except (OSError, ValueError, TypeError, KeyError, BookingError,
                ET.ParseError, ArithmeticError, RecursionError) as error:
            raise StorageError(f"Не удалось загрузить файл: {error}") from error

    @abstractmethod
    def dumps(self, document: dict[str, Any]) -> str:
        """Сериализовать документ."""

    @abstractmethod
    def loads(self, text: str) -> Any:
        """Прочитать документ."""


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Не позволять повторному ключу незаметно заменить значение JSON."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StorageError(f"Повторяющийся ключ: {key}.")
        result[key] = value
    return result


class JsonStorage(DataStorage):
    """Хранение в читаемом JSON с русскими строками."""

    def dumps(self, document: dict[str, Any]) -> str:
        return json.dumps(document, ensure_ascii=False, indent=2) + "\n"

    def loads(self, text: str) -> Any:
        return json.loads(text, object_pairs_hook=unique_object)


class XmlStorage(DataStorage):
    """XML с явным типом узла для точного восстановления значений."""

    def dumps(self, document: dict[str, Any]) -> str:
        root = self._to_element("booking_system", document)
        ET.indent(root, space="  ")
        # Буквальный CR XML-парсер заменяет на LF; ссылка на символ сохраняет CR.
        return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
            root, encoding="unicode"
        ).replace("\r", "&#13;") + "\n"

    def loads(self, text: str) -> Any:
        root = ET.fromstring(text)
        if root.tag != "booking_system":
            raise StorageError("Ожидается корневой элемент booking_system.")
        return self._from_element(root)

    def _to_element(self, name: str, value: Any) -> ET.Element:
        node = ET.Element(name)
        if isinstance(value, dict):
            node.set("kind", "object")
            node.extend(self._to_element(key, item) for key, item in value.items())
        elif isinstance(value, list):
            node.set("kind", "list")
            node.extend(self._to_element("item", item) for item in value)
        else:
            node.set("kind", type(value).__name__)
            node.text = str(value).lower() if isinstance(value, bool) else str(value)
        return node

    def _from_element(self, node: ET.Element) -> Any:
        if set(node.attrib) != {"kind"}:
            raise StorageError("Узел XML должен иметь один атрибут kind.")
        kind = node.get("kind")
        if kind in ("object", "list"):
            if (node.text or "").strip() or any(
                (child.tail or "").strip() for child in node
            ):
                raise StorageError("Лишний текст в контейнере XML.")
            if kind == "object":
                return unique_object([
                    (child.tag, self._from_element(child)) for child in node
                ])
            if any(child.tag != "item" for child in node):
                raise StorageError("Массив XML должен содержать элементы item.")
            return [self._from_element(child) for child in node]
        if len(node):
            raise StorageError("Простое значение XML содержит вложенные узлы.")
        text = node.text or ""
        if kind == "str":
            return text
        if kind == "int":
            return int(text)
        if kind == "bool" and text in ("true", "false"):
            return text == "true"
        raise StorageError("Неизвестный тип значения XML.")
