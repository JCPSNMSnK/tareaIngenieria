"""Casos de uso del sistema de reservas de laboratorio."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from lab_reservations.application.ports import InventoryRepository, ReservationRepository
from lab_reservations.domain.entities import (
    EquipmentUnit,
    Reservation,
    ReservationStatus,
)
from lab_reservations.domain.exceptions import (
    ReservationNotFoundError,
    ReservationOverlapError,
    UnknownUnitError,
)
from lab_reservations.domain.value_objects import TimeInterval, normalize_requester


def _default_local_clock() -> datetime:
    """Reloj local sin microsegundos ni zona horaria para metadatos de auditoría."""
    return datetime.now().replace(microsecond=0)


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    """Resultado determinista de consultar la disponibilidad de una unidad."""

    unit_id: str
    interval: TimeInterval
    available: bool
    conflicting_reservation_ids: tuple[str, ...]


class ReservationService:
    """Orquesta disponibilidad, reservas, cancelaciones y consulta de historial."""

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reservation_repo: ReservationRepository,
        clock: Callable[[], datetime] = _default_local_clock,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reservation_repo = reservation_repo
        self._clock = clock

    def _validate_unit_and_interval(
        self, unit_id: str, start: str, end: str
    ) -> tuple[EquipmentUnit, TimeInterval]:
        """Ruta común obligatoria de validación para disponibilidad y creación (RN-07)."""
        if not isinstance(unit_id, str):
            raise UnknownUnitError(str(unit_id))
        unit = self._inventory_repo.get_unit(unit_id)
        if unit is None:
            raise UnknownUnitError(unit_id)
        interval = TimeInterval.from_iso(start, end)
        return unit, interval

    def _find_active_conflicts(
        self, unit_id: str, candidate: TimeInterval
    ) -> tuple[str, ...]:
        """Obtiene los IDs de reservas activas de la misma unidad que se superponen con candidate."""
        return tuple(
            res.id
            for res in self._reservation_repo.list_all()
            if res.unit_id == unit_id and res.blocks_interval(candidate)
        )

    def list_units(self) -> list[EquipmentUnit]:
        """Lista el inventario físico precargado (RF-01)."""
        return self._inventory_repo.list_units()

    def check_availability(
        self, unit_id: str, start: str, end: str
    ) -> AvailabilityResult:
        """Consulta disponibilidad aplicando las mismas reglas que create_reservation (RF-02, RN-07)."""
        unit, interval = self._validate_unit_and_interval(unit_id, start, end)
        with self._reservation_repo.atomic():
            conflicts = self._find_active_conflicts(unit.id, interval)
        return AvailabilityResult(
            unit_id=unit.id,
            interval=interval,
            available=len(conflicts) == 0,
            conflicting_reservation_ids=conflicts,
        )

    def create_reservation(
        self, unit_id: str, requester: str, start: str, end: str
    ) -> Reservation:
        """Crea una reserva activa tras validar unidad, solicitante, intervalo y no-superposición (RF-03)."""
        unit, interval = self._validate_unit_and_interval(unit_id, start, end)
        cleaned_requester = normalize_requester(requester)

        with self._reservation_repo.atomic():
            conflicts = self._find_active_conflicts(unit.id, interval)
            if conflicts:
                raise ReservationOverlapError(
                    unit_id=unit.id,
                    conflicting_reservation_ids=conflicts,
                )
            reservation_id = self._reservation_repo.next_id()
            reservation = Reservation(
                id=reservation_id,
                unit_id=unit.id,
                requester=cleaned_requester,
                interval=interval,
                status=ReservationStatus.ACTIVE,
                created_at=self._clock(),
            )
            self._reservation_repo.save(reservation)
            return reservation

    def cancel_reservation(self, reservation_id: str) -> Reservation:
        """Cancela lógicamente una reserva conservando su ID y datos y liberando el horario (RF-04)."""
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ReservationNotFoundError(str(reservation_id))

        with self._reservation_repo.atomic():
            existing = self._reservation_repo.get_by_id(reservation_id)
            if existing is None:
                raise ReservationNotFoundError(reservation_id)
            cancelled = existing.cancel(cancelled_at=self._clock())
            self._reservation_repo.save(cancelled)
            return cancelled

    def get_reservation(self, reservation_id: str) -> Reservation:
        """Obtiene el detalle de una reserva activa o cancelada por su ID (RF-05)."""
        if not isinstance(reservation_id, str) or not reservation_id.strip():
            raise ReservationNotFoundError(str(reservation_id))
        existing = self._reservation_repo.get_by_id(reservation_id)
        if existing is None:
            raise ReservationNotFoundError(reservation_id)
        return existing

    def list_reservations(
        self,
        unit_id: str | None = None,
        status: ReservationStatus | None = None,
    ) -> list[Reservation]:
        """Lista el historial de reservas con filtros opcionales por unidad y estado (RF-05)."""
        if unit_id is not None and self._inventory_repo.get_unit(unit_id) is None:
            raise UnknownUnitError(unit_id)

        items = self._reservation_repo.list_all()
        if unit_id is not None:
            items = [r for r in items if r.unit_id == unit_id]
        if status is not None:
            items = [r for r in items if r.status == status]
        return items
