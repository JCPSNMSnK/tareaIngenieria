"""Adaptadores locales de persistencia en archivos JSON con escritura atómica."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
from typing import Any, Iterator

from lab_reservations.domain import (
    EquipmentUnit,
    Reservation,
    ReservationStatus,
    TimeInterval,
    format_local_iso_datetime,
    parse_local_iso_datetime,
)


class DataStorageError(RuntimeError):
    """Error de lectura, integridad o escritura en los archivos JSON de persistencia."""


class JsonInventoryRepository:
    """Repositorio de solo lectura sobre el catálogo fijo data/inventory.json."""

    def __init__(self, inventory_path: Path) -> None:
        self._path = Path(inventory_path)
        self._units = self._load_units()
        self._by_id = {u.id: u for u in self._units}

    @property
    def path(self) -> Path:
        return self._path

    def _load_units(self) -> tuple[EquipmentUnit, ...]:
        if not self._path.exists():
            raise DataStorageError(
                f"No existe el archivo de inventario precargado: {self._path}"
            )
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataStorageError(
                f"Error al leer el inventario precargado en {self._path}: {exc}"
            ) from exc

        if not isinstance(raw, list) or not raw:
            raise DataStorageError(
                f"El inventario en {self._path} debe ser una lista JSON no vacía."
            )

        units: list[EquipmentUnit] = []
        seen_ids: set[str] = set()
        for entry in raw:
            if not isinstance(entry, dict) or "id" not in entry or "name" not in entry:
                raise DataStorageError(
                    f"Entrada de inventario inválida en {self._path}: {entry!r}"
                )
            unit = EquipmentUnit(id=entry["id"], name=entry["name"])
            if unit.id in seen_ids:
                raise DataStorageError(
                    f"ID de unidad duplicado '{unit.id}' en {self._path}."
                )
            seen_ids.add(unit.id)
            units.append(unit)
        return tuple(units)

    def list_units(self) -> list[EquipmentUnit]:
        return list(self._units)

    def get_unit(self, unit_id: str) -> EquipmentUnit | None:
        return self._by_id.get(unit_id)


@dataclass
class _StoreState:
    schema_version: int
    next_sequence: int
    reservations: list[Reservation]


class JsonReservationRepository:
    """Repositorio JSON de reservas con exclusión mutua y escritura atómica (.tmp + os.replace)."""

    SCHEMA_VERSION = 1

    def __init__(self, reservations_path: Path, *, reset: bool = False) -> None:
        self._path = Path(reservations_path)
        # RLock permite anidar llamadas del repositorio dentro de `with repo.atomic():`
        # manteniendo exclusión mutua real entre hilos concurrentes del proceso local.
        self._lock = threading.RLock()
        if reset:
            self.reset_empty()
        else:
            self.ensure_initialized()

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def atomic(self) -> Iterator[None]:
        with self._lock:
            yield

    def ensure_initialized(self) -> bool:
        """Inicializa el archivo vacío solo si no existe; valida su esquema si ya existe.

        Retorna True si creó un archivo nuevo, False si reutilizó el existente.
        """
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if not self._path.exists():
                self._write_state_unlocked(
                    _StoreState(
                        schema_version=self.SCHEMA_VERSION,
                        next_sequence=1,
                        reservations=[],
                    )
                )
                return True
            # Verifica que el archivo existente sea legible y consistente al arrancar
            self._read_state_unlocked()
            return False

    def reset_empty(self) -> None:
        """Restablece el almacén de reservas a vacío de forma atómica (borra historial)."""
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._write_state_unlocked(
                _StoreState(
                    schema_version=self.SCHEMA_VERSION,
                    next_sequence=1,
                    reservations=[],
                )
            )

    def next_id(self) -> str:
        with self._lock:
            state = self._read_state_unlocked()
            seq = state.next_sequence
            state.next_sequence = seq + 1
            self._write_state_unlocked(state)
            return f"RES-{seq:04d}"

    def save(self, reservation: Reservation) -> None:
        """Inserta una nueva reserva o actualiza su estado en el lugar sin eliminar registros."""
        with self._lock:
            state = self._read_state_unlocked()
            replaced = False
            for idx, existing in enumerate(state.reservations):
                if existing.id == reservation.id:
                    state.reservations[idx] = reservation
                    replaced = True
                    break
            if not replaced:
                state.reservations.append(reservation)
            self._write_state_unlocked(state)

    def get_by_id(self, reservation_id: str) -> Reservation | None:
        with self._lock:
            state = self._read_state_unlocked()
            for item in state.reservations:
                if item.id == reservation_id:
                    return item
            return None

    def list_all(self) -> list[Reservation]:
        with self._lock:
            state = self._read_state_unlocked()
            return list(state.reservations)

    def _read_state_unlocked(self) -> _StoreState:
        if not self._path.exists():
            return _StoreState(
                schema_version=self.SCHEMA_VERSION,
                next_sequence=1,
                reservations=[],
            )
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataStorageError(
                f"Error al leer el archivo de reservas {self._path}: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise DataStorageError(
                f"Estructura raíz inválida en {self._path}: se esperaba un objeto JSON."
            )

        schema_version = payload.get("schema_version")
        next_sequence = payload.get("next_sequence")
        raw_items = payload.get("reservations")

        if schema_version != self.SCHEMA_VERSION:
            raise DataStorageError(
                f"Versión de esquema no soportada en {self._path}: {schema_version!r}"
            )
        if not isinstance(next_sequence, int) or isinstance(next_sequence, bool) or next_sequence < 1:
            raise DataStorageError(
                f"Contador 'next_sequence' inválido en {self._path}: {next_sequence!r}"
            )
        if not isinstance(raw_items, list):
            raise DataStorageError(
                f"El campo 'reservations' en {self._path} debe ser una lista."
            )

        reservations = [self._deserialize_reservation(item) for item in raw_items]
        return _StoreState(
            schema_version=schema_version,
            next_sequence=next_sequence,
            reservations=reservations,
        )

    def _write_state_unlocked(self, state: _StoreState) -> None:
        payload = {
            "schema_version": state.schema_version,
            "next_sequence": state.next_sequence,
            "reservations": [
                self._serialize_reservation(item) for item in state.reservations
            ],
        }
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp_path = self._path.with_name(f"{self._path.name}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(serialized)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self._path)
        except OSError as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise DataStorageError(
                f"No se pudo persistir atómicamente en {self._path}: {exc}"
            ) from exc

    @staticmethod
    def _serialize_reservation(reservation: Reservation) -> dict[str, Any]:
        return {
            "id": reservation.id,
            "unit_id": reservation.unit_id,
            "requester": reservation.requester,
            "start": reservation.interval.start_iso,
            "end": reservation.interval.end_iso,
            "status": reservation.status.value,
            "created_at": format_local_iso_datetime(reservation.created_at),
            "cancelled_at": (
                format_local_iso_datetime(reservation.cancelled_at)
                if reservation.cancelled_at is not None
                else None
            ),
        }

    def _deserialize_reservation(self, raw: Any) -> Reservation:
        if not isinstance(raw, dict):
            raise DataStorageError(f"Registro de reserva inválido en {self._path}: {raw!r}")
        try:
            interval = TimeInterval.from_iso(raw["start"], raw["end"])
            status = ReservationStatus(raw["status"])
            created_at = parse_local_iso_datetime(raw["created_at"], field_name="created_at")
            cancelled_raw = raw.get("cancelled_at")
            cancelled_at = (
                parse_local_iso_datetime(cancelled_raw, field_name="cancelled_at")
                if cancelled_raw is not None
                else None
            )
            return Reservation(
                id=raw["id"],
                unit_id=raw["unit_id"],
                requester=raw["requester"],
                interval=interval,
                status=status,
                created_at=created_at,
                cancelled_at=cancelled_at,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise DataStorageError(
                f"Datos corruptos al reconstruir reserva desde {self._path}: {exc}"
            ) from exc
