"""Entidades puras y estados del dominio de reservas."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from lab_reservations.domain.exceptions import (
    ReservationAlreadyCancelledError,
    ValidationDomainError,
)
from lab_reservations.domain.value_objects import TimeInterval, normalize_requester


@dataclass(frozen=True, slots=True)
class EquipmentUnit:
    """Unidad física individual perteneciente al inventario del laboratorio."""

    id: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip() or self.id != self.id.strip():
            raise ValidationDomainError("El identificador de unidad es inválido.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationDomainError("El nombre de la unidad no puede ser vacío.")


class ReservationStatus(str, Enum):
    """Estados posibles del ciclo de vida de una reserva."""

    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class Reservation:
    """Entidad de reserva con cancelación lógica inmutable (Adaptación B)."""

    id: str
    unit_id: str
    requester: str
    interval: TimeInterval
    status: ReservationStatus
    created_at: datetime
    cancelled_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip() or self.id != self.id.strip():
            raise ValidationDomainError("El identificador de la reserva es inválido.")
        if (
            not isinstance(self.unit_id, str)
            or not self.unit_id.strip()
            or self.unit_id != self.unit_id.strip()
        ):
            raise ValidationDomainError("El identificador de unidad en la reserva es inválido.")
        object.__setattr__(self, "requester", normalize_requester(self.requester))

        if not isinstance(self.interval, TimeInterval):
            raise ValidationDomainError("El intervalo de la reserva debe ser un TimeInterval válido.")
        if not isinstance(self.status, ReservationStatus):
            raise ValidationDomainError("El estado de la reserva es inválido.")
        if type(self.created_at) is not datetime or self.created_at.tzinfo is not None:
            raise ValidationDomainError(
                "La marca 'created_at' debe ser un datetime local sin zona horaria."
            )
        if self.status == ReservationStatus.ACTIVE and self.cancelled_at is not None:
            raise ValidationDomainError(
                "Una reserva activa no puede tener fecha de cancelación."
            )
        if self.cancelled_at is not None and (
            type(self.cancelled_at) is not datetime or self.cancelled_at.tzinfo is not None
        ):
            raise ValidationDomainError(
                "La marca 'cancelled_at' debe ser un datetime local sin zona horaria."
            )

    def blocks_interval(self, candidate: TimeInterval) -> bool:
        """Indica si esta reserva bloquea disponibilidad para el intervalo candidato (RN-04, RN-05)."""
        return self.status == ReservationStatus.ACTIVE and self.interval.overlaps_with(candidate)

    def cancel(self, cancelled_at: datetime) -> Reservation:
        """Transiciona la reserva de ACTIVE a CANCELLED preservando ID y datos históricos (RF-04, RN-06)."""
        if self.status == ReservationStatus.CANCELLED:
            raise ReservationAlreadyCancelledError(self.id)
        return replace(
            self,
            status=ReservationStatus.CANCELLED,
            cancelled_at=cancelled_at,
        )
