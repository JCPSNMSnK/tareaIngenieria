"""Excepciones puras de la capa de dominio."""

from __future__ import annotations


class DomainError(Exception):
    """Clase base para todos los errores de negocio del dominio."""


class NotFoundDomainError(DomainError):
    """Recurso solicitado inexistente."""


class UnknownUnitError(NotFoundDomainError):
    """La unidad física solicitada no pertenece al inventario precargado (RN-01)."""

    def __init__(self, unit_id: str) -> None:
        self.unit_id = unit_id
        super().__init__(
            f"La unidad '{unit_id}' no existe en el inventario del laboratorio."
        )


class ReservationNotFoundError(NotFoundDomainError):
    """No existe una reserva con el identificador indicado (RN-06)."""

    def __init__(self, reservation_id: str) -> None:
        self.reservation_id = reservation_id
        super().__init__(f"No se encontró la reserva '{reservation_id}'.")


class ValidationDomainError(DomainError):
    """Datos de entrada que violan invariantes de formato o valor del dominio."""


class InvalidRequesterError(ValidationDomainError):
    """El solicitante es nulo, vacío o contiene únicamente espacios (RN-02)."""


class InvalidTimeIntervalError(ValidationDomainError):
    """Las fechas/horas son inválidas o violan start < end / formato local (RN-03, SUP-01)."""


class ConflictDomainError(DomainError):
    """La operación entra en conflicto con el estado actual del dominio."""


class ReservationOverlapError(ConflictDomainError):
    """El intervalo solicitado se superpone con al menos una reserva activa (RN-04)."""

    def __init__(
        self, unit_id: str, conflicting_reservation_ids: tuple[str, ...]
    ) -> None:
        self.unit_id = unit_id
        self.conflicting_reservation_ids = conflicting_reservation_ids
        joined = ", ".join(conflicting_reservation_ids)
        super().__init__(
            f"La unidad '{unit_id}' ya posee reservas activas superpuestas ({joined})."
        )


class ReservationAlreadyCancelledError(ConflictDomainError):
    """Intento de cancelar una reserva que ya se encontraba cancelada (RN-06)."""

    def __init__(self, reservation_id: str) -> None:
        self.reservation_id = reservation_id
        super().__init__(f"La reserva '{reservation_id}' ya se encuentra cancelada.")
