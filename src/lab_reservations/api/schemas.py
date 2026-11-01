"""Esquemas HTTP (Pydantic) de entrada, salida y sobre uniforme de errores."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from lab_reservations.application import AvailabilityResult
from lab_reservations.domain import (
    EquipmentUnit,
    Reservation,
    ReservationStatus,
    format_local_iso_datetime,
)


class UnitResponse(BaseModel):
    """Representación HTTP de una unidad física del inventario."""

    id: str
    name: str

    @classmethod
    def from_domain(cls, unit: EquipmentUnit) -> UnitResponse:
        return cls(id=unit.id, name=unit.name)


class AvailabilityResponse(BaseModel):
    """Respuesta HTTP de consulta de disponibilidad por unidad e intervalo."""

    unit_id: str
    start: str
    end: str
    available: bool
    conflicting_reservation_ids: list[str]

    @classmethod
    def from_domain(cls, result: AvailabilityResult) -> AvailabilityResponse:
        return cls(
            unit_id=result.unit_id,
            start=result.interval.start_iso,
            end=result.interval.end_iso,
            available=result.available,
            conflicting_reservation_ids=list(result.conflicting_reservation_ids),
        )


class CreateReservationRequest(BaseModel):
    """Cuerpo JSON requerido para crear una reserva nueva."""

    model_config = ConfigDict(extra="forbid")

    unit_id: StrictStr
    requester: StrictStr
    start: StrictStr
    end: StrictStr


class ReservationResponse(BaseModel):
    """Representación HTTP de una reserva activa o cancelada."""

    id: str
    unit_id: str
    requester: str
    start: str
    end: str
    status: ReservationStatus
    created_at: str
    cancelled_at: str | None

    @classmethod
    def from_domain(cls, reservation: Reservation) -> ReservationResponse:
        return cls(
            id=reservation.id,
            unit_id=reservation.unit_id,
            requester=reservation.requester,
            start=reservation.interval.start_iso,
            end=reservation.interval.end_iso,
            status=reservation.status,
            created_at=format_local_iso_datetime(reservation.created_at),
            cancelled_at=(
                format_local_iso_datetime(reservation.cancelled_at)
                if reservation.cancelled_at is not None
                else None
            ),
        )


class ErrorDetail(BaseModel):
    """Detalle estructurado de error devuelto por la API."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Sobre estándar de error JSON (`{"error": ...}`)."""

    error: ErrorDetail
