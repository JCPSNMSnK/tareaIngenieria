"""Suite de pruebas automáticas HTTP REST end-to-end y reinicio de aplicación (Episodio 3)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Iterator

from fastapi.testclient import TestClient
import pytest

from lab_reservations.api import create_app

REPO_INVENTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "inventory.json"


@pytest.fixture()
def isolated_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_INVENTORY_PATH, data_dir / "inventory.json")
    return data_dir


@pytest.fixture()
def client(isolated_data_dir: Path) -> Iterator[TestClient]:
    ticks = iter(
        [
            datetime(2026, 11, 3, 8, 0, 0),
            datetime(2026, 11, 3, 8, 5, 0),
            datetime(2026, 11, 3, 8, 10, 0),
            datetime(2026, 11, 3, 8, 15, 0),
        ]
    )
    application = create_app(
        data_dir=isolated_data_dir,
        clock=lambda: next(ticks, datetime(2026, 11, 3, 9, 0, 0)),
    )
    with TestClient(application) as test_client:
        yield test_client


def test_http_get_units_returns_preloaded_inventory(client: TestClient) -> None:
    """RF-01: GET /units expone exactamente las 5 unidades del catálogo precargado."""
    resp = client.get("/units")
    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "MIC-01", "name": "Microscopio digital"},
        {"id": "MIC-02", "name": "Microscopio digital"},
        {"id": "OSC-01", "name": "Osciloscopio"},
        {"id": "MUL-01", "name": "Multímetro"},
        {"id": "FUE-01", "name": "Fuente de alimentación"},
    ]


def test_http_valid_creation_and_availability_check(client: TestClient) -> None:
    """CA-01: POST /reservations crea reserva válida (201) y GET /availability informa bloqueo."""
    avail_before = client.get(
        "/availability",
        params={
            "unit_id": "MIC-01",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert avail_before.status_code == 200
    assert avail_before.json()["available"] is True

    create_resp = client.post(
        "/reservations",
        json={
            "unit_id": "MIC-01",
            "requester": "  Dra. Valeria Méndez (Ficticio)  ",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body == {
        "id": "RES-0001",
        "unit_id": "MIC-01",
        "requester": "Dra. Valeria Méndez (Ficticio)",
        "start": "2026-11-10T10:00",
        "end": "2026-11-10T11:00",
        "status": "ACTIVE",
        "created_at": "2026-11-03T08:00",
        "cancelled_at": None,
    }

    avail_after = client.get(
        "/availability",
        params={
            "unit_id": "MIC-01",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert avail_after.status_code == 200
    assert avail_after.json() == {
        "unit_id": "MIC-01",
        "start": "2026-11-10T10:00",
        "end": "2026-11-10T11:00",
        "available": False,
        "conflicting_reservation_ids": ["RES-0001"],
    }


def test_http_rejects_overlap_and_allows_consecutive_and_other_units(
    client: TestClient,
) -> None:
    """CA-02, CA-03, CA-04: Ejemplo exacto de la consigna (10:00-11:00 vs 10:30-11:30, 11:00-12:00 y MIC-02)."""
    r1 = client.post(
        "/reservations",
        json={
            "unit_id": "MIC-01",
            "requester": "Dra. Valeria Méndez (Ficticio)",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert r1.status_code == 201

    # 1. Superposición 10:30 a 11:30 en MIC-01 -> 409 Conflict
    overlap_resp = client.post(
        "/reservations",
        json={
            "unit_id": "MIC-01",
            "requester": "Ing. Martín Rojas (Ficticio)",
            "start": "2026-11-10T10:30",
            "end": "2026-11-10T11:30",
        },
    )
    assert overlap_resp.status_code == 409
    assert overlap_resp.json()["error"]["code"] == "RESERVATION_OVERLAP"
    assert overlap_resp.json()["error"]["details"]["conflicting_reservation_ids"] == [
        "RES-0001"
    ]

    # 2. Límite consecutivo 11:00 a 12:00 en MIC-01 -> Disponible y 201 Created
    consec_avail = client.get(
        "/availability",
        params={
            "unit_id": "MIC-01",
            "start": "2026-11-10T11:00",
            "end": "2026-11-10T12:00",
        },
    )
    assert consec_avail.status_code == 200
    assert consec_avail.json()["available"] is True

    consec_resp = client.post(
        "/reservations",
        json={
            "unit_id": "MIC-01",
            "requester": "Ing. Martín Rojas (Ficticio)",
            "start": "2026-11-10T11:00",
            "end": "2026-11-10T12:00",
        },
    )
    assert consec_resp.status_code == 201
    assert consec_resp.json()["id"] == "RES-0002"

    # 3. Unidad distinta MIC-02 de 10:00 a 11:00 -> Disponible y 201 Created
    other_unit_avail = client.get(
        "/availability",
        params={
            "unit_id": "MIC-02",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert other_unit_avail.status_code == 200
    assert other_unit_avail.json()["available"] is True

    other_unit_resp = client.post(
        "/reservations",
        json={
            "unit_id": "MIC-02",
            "requester": "Lic. Camila Soto (Ficticio)",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert other_unit_resp.status_code == 201
    assert other_unit_resp.json()["id"] == "RES-0003"


def test_http_invalid_inputs_rejected_symmetrically(client: TestClient) -> None:
    """CA-05, RN-07: Unidad desconocida (404), solicitante vacío (422) y fechas inválidas (422)."""
    # Unidad inexistente en disponibilidad y en creación -> 404
    u_avail = client.get(
        "/availability",
        params={
            "unit_id": "MIC-99",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    u_post = client.post(
        "/reservations",
        json={
            "unit_id": "MIC-99",
            "requester": "Dra. Valeria Méndez (Ficticio)",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
        },
    )
    assert u_avail.status_code == 404
    assert u_post.status_code == 404
    assert u_post.json()["error"]["code"] == "UNKNOWN_UNIT"

    # Solicitante vacío o solo espacios -> 422
    for bad_req in ["", "    "]:
        resp = client.post(
            "/reservations",
            json={
                "unit_id": "OSC-01",
                "requester": bad_req,
                "start": "2026-11-10T10:00",
                "end": "2026-11-10T11:00",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_REQUESTER"

    # Rango invertido / igual / timezone / formato inválido -> 422 en ambos endpoints
    for bad_start, bad_end in [
        ("2026-11-10T11:00", "2026-11-10T11:00"),
        ("2026-11-10T12:00", "2026-11-10T11:00"),
        ("2026-11-10", "2026-11-11"),
        ("2026-11-10T10:00Z", "2026-11-10T11:00Z"),
    ]:
        a_resp = client.get(
            "/availability",
            params={"unit_id": "OSC-01", "start": bad_start, "end": bad_end},
        )
        c_resp = client.post(
            "/reservations",
            json={
                "unit_id": "OSC-01",
                "requester": "Dra. Valeria Méndez (Ficticio)",
                "start": bad_start,
                "end": bad_end,
            },
        )
        assert a_resp.status_code == 422
        assert c_resp.status_code == 422
        assert c_resp.json()["error"]["code"] == "INVALID_TIME_INTERVAL"

    # Esquema JSON con campos extra no permitidos -> 422
    extra_resp = client.post(
        "/reservations",
        json={
            "unit_id": "OSC-01",
            "requester": "Dra. Valeria Méndez (Ficticio)",
            "start": "2026-11-10T10:00",
            "end": "2026-11-10T11:00",
            "campo_extra": "no_permitido",
        },
    )
    assert extra_resp.status_code == 422
    assert extra_resp.json()["error"]["code"] == "REQUEST_VALIDATION_ERROR"


def test_http_cancellation_preserves_record_and_frees_interval(
    client: TestClient,
) -> None:
    """CA-06: Cancelar conserva ID y datos en historial, libera disponibilidad y rechaza doble cancelación."""
    created = client.post(
        "/reservations",
        json={
            "unit_id": "MUL-01",
            "requester": "Dra. Valeria Méndez (Ficticio)",
            "start": "2026-11-12T09:00",
            "end": "2026-11-12T10:30",
        },
    ).json()

    cancel_resp = client.post(f"/reservations/{created['id']}/cancel")
    assert cancel_resp.status_code == 200
    cancelled = cancel_resp.json()
    assert cancelled["id"] == "RES-0001"
    assert cancelled["unit_id"] == "MUL-01"
    assert cancelled["requester"] == "Dra. Valeria Méndez (Ficticio)"
    assert cancelled["start"] == "2026-11-12T09:00"
    assert cancelled["end"] == "2026-11-12T10:30"
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancelled_at"] == "2026-11-03T08:05"

    # Sigue accesible individualmente y en el listado histórico
    detail = client.get("/reservations/RES-0001")
    assert detail.status_code == 200
    assert detail.json() == cancelled

    # Doble cancelación -> 409; ID inexistente -> 404
    assert client.post("/reservations/RES-0001/cancel").status_code == 409
    assert client.post("/reservations/RES-9999/cancel").status_code == 404
    assert client.get("/reservations/RES-9999").status_code == 404

    # El horario quedó liberado para consulta y nueva reserva
    avail = client.get(
        "/availability",
        params={
            "unit_id": "MUL-01",
            "start": "2026-11-12T09:00",
            "end": "2026-11-12T10:30",
        },
    )
    assert avail.json()["available"] is True

    rebooked = client.post(
        "/reservations",
        json={
            "unit_id": "MUL-01",
            "requester": "Ing. Martín Rojas (Ficticio)",
            "start": "2026-11-12T09:00",
            "end": "2026-11-12T10:30",
        },
    )
    assert rebooked.status_code == 201
    assert rebooked.json()["id"] == "RES-0002"

    # Filtros del historial
    cancelled_only = client.get(
        "/reservations", params={"unit_id": "MUL-01", "status": "CANCELLED"}
    )
    assert [r["id"] for r in cancelled_only.json()] == ["RES-0001"]


def test_http_app_restart_recovers_active_and_cancelled_reservations(
    isolated_data_dir: Path,
) -> None:
    """CA-07 vía HTTP: Detener una instancia FastAPI y arrancar una nueva conserva activas y canceladas."""
    with TestClient(create_app(data_dir=isolated_data_dir)) as client_before_restart:
        r1 = client_before_restart.post(
            "/reservations",
            json={
                "unit_id": "MIC-01",
                "requester": "Dra. Valeria Méndez (Ficticio)",
                "start": "2026-11-18T10:00",
                "end": "2026-11-18T11:00",
            },
        )
        r2 = client_before_restart.post(
            "/reservations",
            json={
                "unit_id": "FUE-01",
                "requester": "Ing. Martín Rojas (Ficticio)",
                "start": "2026-11-18T15:00",
                "end": "2026-11-18T16:00",
            },
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        cancel = client_before_restart.post("/reservations/RES-0001/cancel")
        assert cancel.status_code == 200

    # Nueva instancia completa de la aplicación sobre el mismo directorio sin borrar datos
    with TestClient(create_app(data_dir=isolated_data_dir)) as client_after_restart:
        history = client_after_restart.get("/reservations").json()
        assert [(item["id"], item["status"]) for item in history] == [
            ("RES-0001", "CANCELLED"),
            ("RES-0002", "ACTIVE"),
        ]

        # La cancelada sigue liberando el horario; la activa sigue bloqueándolo
        free_check = client_after_restart.get(
            "/availability",
            params={
                "unit_id": "MIC-01",
                "start": "2026-11-18T10:00",
                "end": "2026-11-18T11:00",
            },
        ).json()
        busy_check = client_after_restart.get(
            "/availability",
            params={
                "unit_id": "FUE-01",
                "start": "2026-11-18T15:00",
                "end": "2026-11-18T16:00",
            },
        ).json()
        assert free_check["available"] is True
        assert busy_check["available"] is False
        assert busy_check["conflicting_reservation_ids"] == ["RES-0002"]
