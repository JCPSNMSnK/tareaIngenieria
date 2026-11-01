"""Objetos de valor del dominio (intervalos horarios y normalización)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from lab_reservations.domain.exceptions import (
    InvalidRequesterError,
    InvalidTimeIntervalError,
)

_LOCAL_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")


def parse_local_iso_datetime(raw: str, field_name: str = "datetime") -> datetime:
    """Parsea una fecha-hora ISO-8601 local estricta sin zona horaria (SUP-01)."""
    if not isinstance(raw, str) or not _LOCAL_ISO_PATTERN.match(raw):
        raise InvalidTimeIntervalError(
            f"El campo '{field_name}' debe tener formato ISO local "
            "'YYYY-MM-DDTHH:MM' o 'YYYY-MM-DDTHH:MM:SS' sin zona horaria."
        )
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidTimeIntervalError(
            f"El campo '{field_name}' contiene una fecha u hora calendáricamente inválida: '{raw}'."
        ) from exc

    if parsed.tzinfo is not None:
        raise InvalidTimeIntervalError(
            f"El campo '{field_name}' no debe incluir zona horaria explícita."
        )
    return parsed


def format_local_iso_datetime(value: datetime) -> str:
    """Formatea una fecha-hora local en ISO-8601 legible."""
    if value.second == 0 and value.microsecond == 0:
        return value.strftime("%Y-%m-%dT%H:%M")
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def normalize_requester(raw: str) -> str:
    """Normaliza el nombre del solicitante y rechaza vacíos o solo espacios (RN-02)."""
    if not isinstance(raw, str):
        raise InvalidRequesterError("El solicitante debe ser una cadena de texto válida.")
    cleaned = raw.strip()
    if not cleaned:
        raise InvalidRequesterError(
            "El solicitante no puede ser vacío ni estar compuesto solo por espacios."
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class TimeInterval:
    """Intervalo temporal semiabierto [start, end) en hora local del laboratorio."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if type(self.start) is not datetime or type(self.end) is not datetime:
            raise InvalidTimeIntervalError(
                "Los extremos 'start' y 'end' deben ser instancias de datetime con fecha y hora."
            )
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise InvalidTimeIntervalError(
                "Los extremos 'start' y 'end' deben ser timezone-naive (hora local uniforme)."
            )
        if not (self.start < self.end):
            raise InvalidTimeIntervalError(
                "El inicio del intervalo debe ser estrictamente anterior al fin (start < end)."
            )

    @classmethod
    def from_iso(cls, start_raw: str, end_raw: str) -> TimeInterval:
        """Construye y valida un TimeInterval a partir de cadenas ISO locales."""
        start_dt = parse_local_iso_datetime(start_raw, field_name="start")
        end_dt = parse_local_iso_datetime(end_raw, field_name="end")
        return cls(start=start_dt, end=end_dt)

    def overlaps_with(self, other: TimeInterval) -> bool:
        """Evalúa superposición bajo semántica semiabierta [start, end) (RN-04, Adaptación A)."""
        return self.start < other.end and other.start < self.end

    @property
    def start_iso(self) -> str:
        return format_local_iso_datetime(self.start)

    @property
    def end_iso(self) -> str:
        return format_local_iso_datetime(self.end)
