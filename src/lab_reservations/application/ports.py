"""Puertos (contratos de repositorios) requeridos por la capa de aplicación."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from lab_reservations.domain.entities import EquipmentUnit, Reservation


class InventoryRepository(Protocol):
    """Contrato de solo lectura para acceder al inventario precargado."""

    def list_units(self) -> list[EquipmentUnit]:
        """Devuelve todas las unidades físicas del inventario."""

    def get_unit(self, unit_id: str) -> EquipmentUnit | None:
        """Busca una unidad por coincidencia exacta de su identificador."""


class ReservationRepository(Protocol):
    """Contrato de persistencia para reservas activas y canceladas."""

    def atomic(self) -> AbstractContextManager[None]:
        """Contexto de exclusión mutua para operaciones de lectura-validación-escritura."""

    def next_id(self) -> str:
        """Genera y reserva el próximo identificador único secuencial (ej. RES-0001)."""

    def save(self, reservation: Reservation) -> None:
        """Inserta o actualiza una reserva sin eliminar el registro histórico."""

    def get_by_id(self, reservation_id: str) -> Reservation | None:
        """Recupera una reserva existente (activa o cancelada) por su ID."""

    def list_all(self) -> list[Reservation]:
        """Lista todas las reservas registradas en orden de creación."""
