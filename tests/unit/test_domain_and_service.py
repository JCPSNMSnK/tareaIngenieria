"""Pruebas unitarias puras de la capa de dominio y servicio de aplicación (Episodio 1)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Iterator

import pytest

from lab_reservations.application import ReservationService
from lab_reservations.domain import (
    EquipmentUnit,
    InvalidRequesterError,
    InvalidTimeIntervalError,
    Reservation,
    ReservationAlreadyCancelledError,
    ReservationNotFoundError,
    ReservationOverlapError,
    ReservationStatus,
    TimeInterval,
    UnknownUnitError,
)


class InMemoryInventoryRepository:
    """Adaptador doble en memoria con las 5 unidades precargadas de la especificación."""

    def __init__(self) -> None:
        self._units = [
            EquipmentUnit(id="MIC-01", name="Microscopio digital"),
            EquipmentUnit(id="MIC-02", name="Microscopio digital"),
            EquipmentUnit(id="OSC-01", name="Osciloscopio"),
            EquipmentUnit(id="MUL-01", name="Multímetro"),
            EquipmentUnit(id="FUE-01", name="Fuente de alimentación"),
        ]
        self._by_id = {u.id: u for u in self._units}

    def list_units(self) -> list[EquipmentUnit]:
        return list(self._units)

    def get_unit(self, unit_id: str) -> EquipmentUnit | None:
        return self._by_id.get(unit_id)


class InMemoryReservationRepository:
    """Adaptador doble en memoria para verificar la lógica pura de ReservationService."""

    def __init__(self) -> None:
        self._seq = 1
        self._items: dict[str, Reservation] = {}

    @contextmanager
    def atomic(self) -> Iterator[None]:
        yield

    def next_id(self) -> str:
        res_id = f"RES-{self._seq:04d}"
        self._seq += 1
        return res_id

    def save(self, reservation: Reservation) -> None:
        self._items[reservation.id] = reservation

    def get_by_id(self, reservation_id: str) -> Reservation | None:
        return self._items.get(reservation_id)

    def list_all(self) -> list[Reservation]:
        return list(self._items.values())


@pytest.fixture()
def service() -> ReservationService:
    ticks = iter(
        [
            datetime(2026, 11, 1, 9, 0, 0),
            datetime(2026, 11, 1, 9, 5, 0),
            datetime(2026, 11, 1, 9, 10, 0),
            datetime(2026, 11, 1, 9, 15, 0),
        ]
    )
    return ReservationService(
        inventory_repo=InMemoryInventoryRepository(),
        reservation_repo=InMemoryReservationRepository(),
        clock=lambda: next(ticks, datetime(2026, 11, 1, 10, 0, 0)),
    )


def test_list_preloaded_inventory_units(service: ReservationService) -> None:
    """RF-01: El inventario precargado contiene las 5 unidades físicas exactas."""
    units = service.list_units()
    assert [(u.id, u.name) for u in units] == [
        ("MIC-01", "Microscopio digital"),
        ("MIC-02", "Microscopio digital"),
        ("OSC-01", "Osciloscopio"),
        ("MUL-01", "Multímetro"),
        ("FUE-01", "Fuente de alimentación"),
    ]


def test_valid_creation_and_availability_block(service: ReservationService) -> None:
    """CA-01: Crear una reserva válida asigna ID, estado ACTIVE y ocupa el intervalo."""
    before = service.check_availability(
        "MIC-01", "2026-11-10T10:00", "2026-11-10T11:00"
    )
    assert before.available is True
    assert before.conflicting_reservation_ids == ()

    created = service.create_reservation(
        unit_id="MIC-01",
        requester="  Dra. Valeria Méndez (Ficticio)  ",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )
    assert created.id == "RES-0001"
    assert created.unit_id == "MIC-01"
    assert created.requester == "Dra. Valeria Méndez (Ficticio)"
    assert created.status == ReservationStatus.ACTIVE
    assert created.interval.start_iso == "2026-11-10T10:00"
    assert created.interval.end_iso == "2026-11-10T11:00"
    assert created.cancelled_at is None

    after = service.check_availability(
        "MIC-01", "2026-11-10T10:00", "2026-11-10T11:00"
    )
    assert after.available is False
    assert after.conflicting_reservation_ids == ("RES-0001",)


@pytest.mark.parametrize(
    ("candidate_start", "candidate_end"),
    [
        ("2026-11-10T10:30", "2026-11-10T11:30"),  # ejemplo explícito consigna
        ("2026-11-10T09:30", "2026-11-10T10:30"),  # solape al inicio
        ("2026-11-10T10:15", "2026-11-10T10:45"),  # contenido interno
        ("2026-11-10T09:00", "2026-11-10T12:00"),  # envolvente completo
        ("2026-11-10T10:00", "2026-11-10T11:00"),  # idéntico
    ],
)
def test_overlap_rejected_on_same_active_unit(
    service: ReservationService, candidate_start: str, candidate_end: str
) -> None:
    """CA-02, RN-04: Superposiciones activas en la misma unidad se rechazan en disponibilidad y creación."""
    service.create_reservation(
        unit_id="MIC-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )

    availability = service.check_availability("MIC-01", candidate_start, candidate_end)
    assert availability.available is False
    assert availability.conflicting_reservation_ids == ("RES-0001",)

    with pytest.raises(ReservationOverlapError) as exc_info:
        service.create_reservation(
            unit_id="MIC-01",
            requester="Ing. Martín Rojas (Ficticio)",
            start=candidate_start,
            end=candidate_end,
        )
    assert exc_info.value.conflicting_reservation_ids == ("RES-0001",)
    assert len(service.list_reservations()) == 1


def test_consecutive_boundaries_allowed_on_same_unit(
    service: ReservationService,
) -> None:
    """CA-03, Adaptación A: Turnos consecutivos [10:00, 11:00) y [11:00, 12:00) o [09:00, 10:00) son válidos."""
    service.create_reservation(
        unit_id="MIC-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )

    next_slot = service.check_availability(
        "MIC-01", "2026-11-10T11:00", "2026-11-10T12:00"
    )
    prev_slot = service.check_availability(
        "MIC-01", "2026-11-10T09:00", "2026-11-10T10:00"
    )
    assert next_slot.available is True
    assert prev_slot.available is True

    second = service.create_reservation(
        unit_id="MIC-01",
        requester="Ing. Martín Rojas (Ficticio)",
        start="2026-11-10T11:00",
        end="2026-11-10T12:00",
    )
    third = service.create_reservation(
        unit_id="MIC-01",
        requester="Lic. Camila Soto (Ficticio)",
        start="2026-11-10T09:00",
        end="2026-11-10T10:00",
    )
    assert second.id == "RES-0002"
    assert third.id == "RES-0003"


def test_simultaneous_reservations_allowed_on_distinct_units(
    service: ReservationService,
) -> None:
    """CA-04: Unidades físicas distintas pueden reservarse en el mismo horario."""
    service.create_reservation(
        unit_id="MIC-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )

    mic02_avail = service.check_availability(
        "MIC-02", "2026-11-10T10:00", "2026-11-10T11:00"
    )
    assert mic02_avail.available is True

    mic02_res = service.create_reservation(
        unit_id="MIC-02",
        requester="Ing. Martín Rojas (Ficticio)",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )
    assert mic02_res.id == "RES-0002"
    assert mic02_res.unit_id == "MIC-02"


@pytest.mark.parametrize("bad_unit", ["MIC-99", "mic-01", " MIC-01 ", ""])
def test_unknown_unit_rejected_symmetrically(
    service: ReservationService, bad_unit: str
) -> None:
    """CA-05, RN-01, RN-07: Unidad desconocida falla igual en disponibilidad y en creación."""
    with pytest.raises(UnknownUnitError):
        service.check_availability(bad_unit, "2026-11-10T10:00", "2026-11-10T11:00")

    with pytest.raises(UnknownUnitError):
        service.create_reservation(
            unit_id=bad_unit,
            requester="Dra. Valeria Méndez (Ficticio)",
            start="2026-11-10T10:00",
            end="2026-11-10T11:00",
        )


@pytest.mark.parametrize("bad_requester", ["", "   ", "\t\n  "])
def test_empty_or_whitespace_requester_rejected(
    service: ReservationService, bad_requester: str
) -> None:
    """CA-05, RN-02: Solicitante vacío o de solo espacios es rechazado."""
    with pytest.raises(InvalidRequesterError):
        service.create_reservation(
            unit_id="OSC-01",
            requester=bad_requester,
            start="2026-11-10T10:00",
            end="2026-11-10T11:00",
        )


@pytest.mark.parametrize(
    ("bad_start", "bad_end"),
    [
        ("2026-11-10T11:00", "2026-11-10T11:00"),  # start == end
        ("2026-11-10T12:00", "2026-11-10T11:00"),  # start > end
        ("2026-11-10", "2026-11-11"),              # solo fecha sin hora
        ("2026-11-10 10:00", "2026-11-10 11:00"),  # sin separador ISO 'T'
        ("2026-02-30T10:00", "2026-02-30T11:00"),  # fecha inexistente
        ("2026-11-10T10:00Z", "2026-11-10T11:00Z"),  # timezone UTC explícita
        ("2026-11-10T10:00-03:00", "2026-11-10T11:00-03:00"),  # offset explícito
        ("fecha-invalida", "2026-11-10T11:00"),
    ],
)
def test_invalid_dates_and_ranges_rejected_symmetrically(
    service: ReservationService, bad_start: str, bad_end: str
) -> None:
    """CA-05, RN-03, RN-07, SUP-01: Fechas o rangos inválidos fallan igual en disponibilidad y creación."""
    with pytest.raises(InvalidTimeIntervalError):
        service.check_availability("OSC-01", bad_start, bad_end)

    with pytest.raises(InvalidTimeIntervalError):
        service.create_reservation(
            unit_id="OSC-01",
            requester="Dra. Valeria Méndez (Ficticio)",
            start=bad_start,
            end=bad_end,
        )


def test_time_interval_direct_constructor_guards() -> None:
    """Adaptación A: TimeInterval rechaza objetos date sin hora o datetimes con tzinfo."""
    with pytest.raises(InvalidTimeIntervalError):
        TimeInterval(start=date(2026, 11, 10), end=date(2026, 11, 11))  # type: ignore[arg-type]

    aware_start = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
    aware_end = datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(InvalidTimeIntervalError):
        TimeInterval(start=aware_start, end=aware_end)


def test_historical_past_dates_permitted_by_design(service: ReservationService) -> None:
    """SUP-02: Se permiten fechas pasadas calendáricamente válidas para reproducibilidad determinista."""
    res = service.create_reservation(
        unit_id="MUL-01",
        requester="Ing. Martín Rojas (Ficticio)",
        start="2020-03-15T08:00",
        end="2020-03-15T09:30",
    )
    assert res.status == ReservationStatus.ACTIVE


def test_cancellation_preserves_history_and_frees_slot(
    service: ReservationService,
) -> None:
    """CA-06, RF-04, RN-05, RN-06: Cancelar conserva ID y datos, cambia a CANCELLED y libera el horario."""
    original = service.create_reservation(
        unit_id="FUE-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )

    cancelled = service.cancel_reservation(original.id)
    assert cancelled.id == original.id
    assert cancelled.unit_id == original.unit_id
    assert cancelled.requester == original.requester
    assert cancelled.interval == original.interval
    assert cancelled.created_at == original.created_at
    assert cancelled.status == ReservationStatus.CANCELLED
    assert cancelled.cancelled_at == datetime(2026, 11, 1, 9, 5, 0)

    # Sigue en el historial recuperable por ID y listado
    fetched = service.get_reservation(original.id)
    assert fetched == cancelled

    # El horario vuelve a estar disponible y admite nueva reserva activa
    avail = service.check_availability(
        "FUE-01", "2026-11-10T10:00", "2026-11-10T11:00"
    )
    assert avail.available is True
    assert avail.conflicting_reservation_ids == ()

    rebooked = service.create_reservation(
        unit_id="FUE-01",
        requester="Lic. Camila Soto (Ficticio)",
        start="2026-11-10T10:00",
        end="2026-11-10T11:00",
    )
    assert rebooked.id == "RES-0002"
    assert rebooked.status == ReservationStatus.ACTIVE

    all_history = service.list_reservations(unit_id="FUE-01")
    assert [(r.id, r.status) for r in all_history] == [
        ("RES-0001", ReservationStatus.CANCELLED),
        ("RES-0002", ReservationStatus.ACTIVE),
    ]


def test_cancel_errors_for_missing_or_already_cancelled(
    service: ReservationService,
) -> None:
    """RN-06: Cancelar reserva inexistente o ya cancelada lanza error específico del dominio."""
    with pytest.raises(ReservationNotFoundError):
        service.cancel_reservation("RES-9999")

    res = service.create_reservation(
        unit_id="OSC-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-10T14:00",
        end="2026-11-10T15:00",
    )
    service.cancel_reservation(res.id)

    with pytest.raises(ReservationAlreadyCancelledError):
        service.cancel_reservation(res.id)
