"""Pruebas de integración de persistencia JSON atómica, comando manage_data y reinicio (Episodio 2)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import shutil

import pytest

from lab_reservations.application import ReservationService
from lab_reservations.domain import ReservationOverlapError, ReservationStatus
from lab_reservations.infrastructure import (
    DataStorageError,
    JsonInventoryRepository,
    JsonReservationRepository,
)
from lab_reservations.scripts.manage_data import main as manage_data_main

REPO_INVENTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "inventory.json"


@pytest.fixture()
def isolated_data_dir(tmp_path: Path) -> Path:
    """Copia el inventario oficial a un directorio temporal aislado para pruebas reales en disco."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_INVENTORY_PATH, data_dir / "inventory.json")
    return data_dir


def _build_service(data_dir: Path) -> ReservationService:
    ticks = iter(
        [
            datetime(2026, 11, 2, 10, 0, 0),
            datetime(2026, 11, 2, 10, 5, 0),
            datetime(2026, 11, 2, 10, 10, 0),
            datetime(2026, 11, 2, 10, 15, 0),
        ]
    )
    return ReservationService(
        inventory_repo=JsonInventoryRepository(data_dir / "inventory.json"),
        reservation_repo=JsonReservationRepository(data_dir / "reservations.json"),
        clock=lambda: next(ticks, datetime(2026, 11, 2, 11, 0, 0)),
    )


def test_official_preloaded_inventory_loads_exact_five_units() -> None:
    """RF-01: El archivo versionado data/inventory.json contiene las 5 unidades de la consigna."""
    repo = JsonInventoryRepository(REPO_INVENTORY_PATH)
    units = repo.list_units()
    assert [(u.id, u.name) for u in units] == [
        ("MIC-01", "Microscopio digital"),
        ("MIC-02", "Microscopio digital"),
        ("OSC-01", "Osciloscopio"),
        ("MUL-01", "Multímetro"),
        ("FUE-01", "Fuente de alimentación"),
    ]


def test_survival_of_active_and_cancelled_reservations_across_restart(
    isolated_data_dir: Path,
) -> None:
    """CA-07, Skill Sección 4: Activas y canceladas sobreviven íntegras al detener y reiniciar."""
    inventory_bytes_before = (isolated_data_dir / "inventory.json").read_bytes()

    # Instancia #1: crea dos reservas y cancela la primera
    service_instance_1 = _build_service(isolated_data_dir)
    res_1 = service_instance_1.create_reservation(
        unit_id="MIC-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-15T10:00",
        end="2026-11-15T11:00",
    )
    res_2 = service_instance_1.create_reservation(
        unit_id="OSC-01",
        requester="Ing. Martín Rojas (Ficticio)",
        start="2026-11-15T14:00",
        end="2026-11-15T15:30",
    )
    cancelled_res_1 = service_instance_1.cancel_reservation(res_1.id)

    # Descarta por completo la instancia #1 en memoria y levanta una instancia #2 limpia
    del service_instance_1
    service_instance_2 = _build_service(isolated_data_dir)

    # 1. RES-0001 sigue en el historial con estado CANCELLED y su horario está libre
    recovered_1 = service_instance_2.get_reservation("RES-0001")
    assert recovered_1 == cancelled_res_1
    assert recovered_1.status == ReservationStatus.CANCELLED
    assert recovered_1.requester == "Dra. Valeria Méndez (Ficticio)"
    avail_1 = service_instance_2.check_availability(
        "MIC-01", "2026-11-15T10:00", "2026-11-15T11:00"
    )
    assert avail_1.available is True

    # 2. RES-0002 sigue en estado ACTIVE y bloquea su horario tras el reinicio
    recovered_2 = service_instance_2.get_reservation("RES-0002")
    assert recovered_2 == res_2
    assert recovered_2.status == ReservationStatus.ACTIVE
    avail_2 = service_instance_2.check_availability(
        "OSC-01", "2026-11-15T14:00", "2026-11-15T15:30"
    )
    assert avail_2.available is False
    assert avail_2.conflicting_reservation_ids == ("RES-0002",)

    # 3. Nueva reserva en instancia #2 recibe RES-0003 sin colisión y no deja temporales .tmp
    res_3 = service_instance_2.create_reservation(
        unit_id="MIC-01",
        requester="Lic. Camila Soto (Ficticio)",
        start="2026-11-15T10:00",
        end="2026-11-15T11:00",
    )
    assert res_3.id == "RES-0003"
    assert not (isolated_data_dir / "reservations.json.tmp").exists()

    # 4. Verificación directa sobre el JSON en disco: cero borrado físico e inventario intacto
    raw_disk = json.loads(
        (isolated_data_dir / "reservations.json").read_text(encoding="utf-8")
    )
    assert raw_disk["schema_version"] == 1
    assert raw_disk["next_sequence"] == 4
    assert [item["id"] for item in raw_disk["reservations"]] == [
        "RES-0001",
        "RES-0002",
        "RES-0003",
    ]
    assert (isolated_data_dir / "inventory.json").read_bytes() == inventory_bytes_before


def test_manage_data_init_and_reset_commands(
    isolated_data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skill Sección 3: `init` preserva reservas existentes; `reset` exige `--confirm` y advierte borrado."""
    inventory_bytes_before = (isolated_data_dir / "inventory.json").read_bytes()

    # 1. init crea el archivo vacío cuando no existe
    exit_init_1 = manage_data_main(["--data-dir", str(isolated_data_dir), "init"])
    out_1 = capsys.readouterr()
    assert exit_init_1 == 0
    assert "creado vacío" in out_1.out

    # Agrega una reserva real
    service = _build_service(isolated_data_dir)
    service.create_reservation(
        unit_id="MUL-01",
        requester="Dra. Valeria Méndez (Ficticio)",
        start="2026-11-20T09:00",
        end="2026-11-20T10:00",
    )

    # 2. Segundo init NO borra las reservas existentes
    exit_init_2 = manage_data_main(["--data-dir", str(isolated_data_dir), "init"])
    out_2 = capsys.readouterr()
    assert exit_init_2 == 0
    assert "1 reservas preservadas" in out_2.out

    # 3. reset sin --confirm falla de forma segura y conserva las reservas
    exit_reset_no_confirm = manage_data_main(
        ["--data-dir", str(isolated_data_dir), "reset"]
    )
    out_3 = capsys.readouterr()
    assert exit_reset_no_confirm == 2
    assert "BORRA permanentemente" in out_3.err
    assert len(_build_service(isolated_data_dir).list_reservations()) == 1

    # 4. reset --confirm limpia las reservas, advierte y mantiene intacto inventory.json
    exit_reset_confirmed = manage_data_main(
        ["--data-dir", str(isolated_data_dir), "reset", "--confirm"]
    )
    out_4 = capsys.readouterr()
    assert exit_reset_confirmed == 0
    assert "Se han borrado todas las reservas" in out_4.out
    assert _build_service(isolated_data_dir).list_reservations() == []
    assert (isolated_data_dir / "inventory.json").read_bytes() == inventory_bytes_before


def test_local_thread_safety_prevents_double_booking(isolated_data_dir: Path) -> None:
    """SUP-05: Solicitudes concurrentes sobre la misma unidad e intervalo admiten exactamente 1 activa."""
    service = _build_service(isolated_data_dir)

    def attempt(idx: int) -> str:
        try:
            created = service.create_reservation(
                unit_id="FUE-01",
                requester=f"Solicitante Ficticio {idx}",
                start="2026-11-25T10:00",
                end="2026-11-25T11:00",
            )
            return created.id
        except ReservationOverlapError:
            return "CONFLICT"

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(attempt, range(6)))

    created_ids = [item for item in outcomes if item != "CONFLICT"]
    assert created_ids == ["RES-0001"]
    assert outcomes.count("CONFLICT") == 5


def test_corrupted_json_raises_storage_error(isolated_data_dir: Path) -> None:
    """Integridad de almacenamiento: JSON malformado lanza DataStorageError explícito."""
    bad_file = isolated_data_dir / "reservations.json"
    bad_file.write_text("{corrupto", encoding="utf-8")

    with pytest.raises(DataStorageError):
        JsonReservationRepository(bad_file)
