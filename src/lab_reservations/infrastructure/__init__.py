"""API pública de adaptadores de infraestructura."""

from lab_reservations.infrastructure.json_repositories import (
    DataStorageError,
    JsonInventoryRepository,
    JsonReservationRepository,
)

__all__ = [
    "DataStorageError",
    "JsonInventoryRepository",
    "JsonReservationRepository",
]
