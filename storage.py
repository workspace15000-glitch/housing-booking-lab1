"""Чтение и запись данных в JSON и XML."""

import json
from xml.etree import ElementTree as ET

from booking_system import BookingSystem
from models import (
    Accommodation, Address, Amenity, Apartment, Booking, BookingPeriod, Guest, Host,
    House, Room, Rules,
)


class FileStorage:
    def to_data(self, system: BookingSystem) -> dict:
        data = {name: [] for name in system.data}
        for name in ("hosts", "guests"):
            for person in system.get_all(name):
                data[name].append({"id": person.id, "name": person.name,
                                   "phone": person.phone})
        for housing in system.get_all("housing"):
            row = {
                "id": housing.id, "type": housing.kind(), "title": housing.title,
                "host_id": housing.host_id, "city": housing.address.city,
                "street": housing.address.street, "building": housing.address.building,
                "price": housing.price, "capacity": housing.capacity,
                "amenities": [item.name for item in housing.amenities],
                "pets_allowed": housing.rules.pets_allowed,
                "smoking_allowed": housing.rules.smoking_allowed,
            }
            if isinstance(housing, Apartment):
                row["rooms"] = housing.rooms
            elif isinstance(housing, House):
                row["floors"] = housing.floors
            elif isinstance(housing, Room):
                row["shared_bathroom"] = housing.shared_bathroom
            data["housing"].append(row)
        for booking in system.get_all("bookings"):
            data["bookings"].append({
                "id": booking.id, "guest_id": booking.guest_id,
                "accommodation_id": booking.accommodation_id,
                "check_in": booking.period.check_in.isoformat(),
                "check_out": booking.period.check_out.isoformat(),
                "guest_count": booking.guest_count,
                "price": booking.price, "status": booking.status,
            })
        return data

    def from_data(self, data: dict) -> BookingSystem:
        if not isinstance(data, dict) or set(data) != {
            "hosts", "guests", "housing", "bookings"
        }:
            raise ValueError("В файле должны быть четыре коллекции данных.")
        system = BookingSystem()
        for rows in data.values():
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise ValueError("Коллекции должны содержать записи объектов.")
        for name, person_class in (("hosts", Host), ("guests", Guest)):
            for row in data[name]:
                system.add(name, person_class(**row))
        classes = {"apartment": Apartment, "house": House,
                   "room": Room, "housing": Accommodation}
        for saved_row in data["housing"]:
            row = saved_row.copy()
            housing_class = classes[row.pop("type")]
            row["address"] = Address(row.pop("city"), row.pop("street"),
                                     row.pop("building"))
            row["rules"] = Rules(row.pop("pets_allowed"), row.pop("smoking_allowed"))
            row["amenities"] = [Amenity(name) for name in row["amenities"]]
            system.add("housing", housing_class(**row))
        for saved_row in data["bookings"]:
            row = saved_row.copy()
            row["period"] = BookingPeriod(row.pop("check_in"), row.pop("check_out"))
            system.add("bookings", Booking(**row))
        return system

    def save_json(self, system: BookingSystem, path: str) -> None:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(self.to_data(system), file, ensure_ascii=False, indent=2)

    def load_json(self, path: str) -> BookingSystem:
        with open(path, encoding="utf-8") as file:
            return self.from_data(json.load(file))

    def save_xml(self, system: BookingSystem, path: str) -> None:
        root = ET.Element("booking_system")
        for collection, rows in self.to_data(system).items():
            group = ET.SubElement(root, collection)
            for row in rows:
                record = ET.SubElement(group, "record")
                for name, value in row.items():
                    element = ET.SubElement(record, name)
                    if name == "amenities":
                        for amenity in value:
                            ET.SubElement(element, "amenity").text = amenity
                    else:
                        element.text = str(value)
        ET.indent(root, space="  ")
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

    def load_xml(self, path: str) -> BookingSystem:
        root = ET.parse(path).getroot()
        if root.tag != "booking_system":
            raise ValueError("Неверный корневой элемент XML.")
        number_fields = {"price", "capacity", "rooms", "floors", "guest_count"}
        bool_fields = {"pets_allowed", "smoking_allowed", "shared_bathroom"}
        data = {}
        for group in root:
            data[group.tag] = []
            for record in group:
                row = {}
                for field in record:
                    value = field.text or ""
                    if field.tag == "amenities":
                        value = [item.text or "" for item in field]
                    elif field.tag in number_fields:
                        value = int(value)
                    elif field.tag in bool_fields:
                        if value not in ("True", "False"):
                            raise ValueError("Неверное логическое значение XML.")
                        value = value == "True"
                    row[field.tag] = value
                data[group.tag].append(row)
        return self.from_data(data)
