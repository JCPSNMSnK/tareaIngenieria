"""Comando local para inicialización segura (`init`) y reinicio (`reset`) de datos.

Uso:
    python -m lab_reservations.scripts.manage_data init
    python -m lab_reservations.scripts.manage_data reset --confirm
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Sequence

from lab_reservations.infrastructure import (
    DataStorageError,
    JsonInventoryRepository,
    JsonReservationRepository,
)


def default_data_dir() -> Path:
    """Resuelve el directorio `data/` por defecto en la raíz del repositorio."""
    env_dir = os.environ.get("LAB_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[3] / "data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lab_reservations.scripts.manage_data",
        description=(
            "Gestiona la carga inicial y el reinicio explícito de la persistencia JSON local."
        ),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Ruta opcional al directorio de datos (por defecto: ./data).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "init",
        help=(
            "Verifica data/inventory.json e inicializa data/reservations.json "
            "únicamente si no existe (NO borra reservas existentes)."
        ),
    )

    reset_parser = subparsers.add_parser(
        "reset",
        help=(
            "Restablece data/reservations.json a estado vacío conservando el inventario. "
            "ADVERTENCIA: borra todas las reservas activas y canceladas."
        ),
    )
    reset_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirma explícitamente el borrado irreversible del historial de reservas.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    data_dir: Path = args.data_dir if args.data_dir is not None else default_data_dir()
    inventory_path = data_dir / "inventory.json"
    reservations_path = data_dir / "reservations.json"

    try:
        inventory_repo = JsonInventoryRepository(inventory_path)
    except DataStorageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    units = inventory_repo.list_units()

    if args.command == "init":
        existed_before = reservations_path.exists()
        try:
            reservation_repo = JsonReservationRepository(reservations_path)
            existing = reservation_repo.list_all()
        except DataStorageError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        action_note = "reutilizado" if existed_before else "creado vacío"
        print(
            f"OK [init]: Inventario verificado ({len(units)} unidades en '{inventory_path}'). "
            f"Almacén de reservas {action_note} en '{reservations_path}' "
            f"({len(existing)} reservas preservadas)."
        )
        return 0

    if args.command == "reset":
        if not args.confirm:
            print(
                "ADVERTENCIA: El comando 'reset' BORRA permanentemente todas las reservas "
                f"activas y canceladas en '{reservations_path}' (el catálogo '{inventory_path}' "
                "se conserva). Ejecute nuevamente agregando '--confirm' si desea continuar.",
                file=sys.stderr,
            )
            return 2

        try:
            JsonReservationRepository(reservations_path, reset=True)
        except DataStorageError as exc:
            print(f"ERROR al reiniciar datos: {exc}", file=sys.stderr)
            return 1

        print(
            "ADVERTENCIA APLICADA [reset]: Se han borrado todas las reservas activas y "
            f"canceladas en '{reservations_path}'. El inventario precargado "
            f"({len(units)} unidades en '{inventory_path}') permanece intacto."
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
