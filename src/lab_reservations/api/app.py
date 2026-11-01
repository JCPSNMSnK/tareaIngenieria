"""Aplicación HTTP REST local (FastAPI) y traducción determinista de errores de dominio."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from lab_reservations import __version__
from lab_reservations.api.schemas import (
    AvailabilityResponse,
    CreateReservationRequest,
    ErrorDetail,
    ErrorEnvelope,
    ReservationResponse,
    UnitResponse,
)
from lab_reservations.application import ReservationService
from lab_reservations.domain import (
    InvalidRequesterError,
    InvalidTimeIntervalError,
    ReservationAlreadyCancelledError,
    ReservationNotFoundError,
    ReservationOverlapError,
    ReservationStatus,
    UnknownUnitError,
    ValidationDomainError,
)
from lab_reservations.infrastructure import (
    DataStorageError,
    JsonInventoryRepository,
    JsonReservationRepository,
)
from lab_reservations.scripts.manage_data import default_data_dir


_HTTP_422: int = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


def _build_reservation_service(
    data_dir: Path | None,
    clock: Callable[[], datetime] | None,
) -> ReservationService:
    resolved_dir = data_dir if data_dir is not None else default_data_dir()
    inventory_repo = JsonInventoryRepository(resolved_dir / "inventory.json")
    reservation_repo = JsonReservationRepository(resolved_dir / "reservations.json")
    if clock is not None:
        return ReservationService(
            inventory_repo=inventory_repo,
            reservation_repo=reservation_repo,
            clock=clock,
        )
    return ReservationService(
        inventory_repo=inventory_repo,
        reservation_repo=reservation_repo,
    )


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details or {},
        )
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump())


def get_reservation_service(request: Request) -> ReservationService:
    """Obtiene el servicio configurado para la instancia actual de la aplicación."""
    service: ReservationService | None = getattr(
        request.app.state, "reservation_service", None
    )
    if service is None:
        service = _build_reservation_service(
            data_dir=request.app.state.configured_data_dir,
            clock=request.app.state.configured_clock,
        )
        request.app.state.reservation_service = service
    return service


def create_app(
    data_dir: Path | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Construye una instancia aislada de la API REST local de reservas de laboratorio."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.reservation_service = _build_reservation_service(
            data_dir=application.state.configured_data_dir,
            clock=application.state.configured_clock,
        )
        yield

    application = FastAPI(
        title="Sistema de Reservas de Laboratorio",
        description="API HTTP REST local y determinista para reservas de equipamiento con historial.",
        version=__version__,
        lifespan=lifespan,
    )
    application.state.configured_data_dir = data_dir
    application.state.configured_clock = clock
    application.state.reservation_service = None

    @application.exception_handler(UnknownUnitError)
    async def handle_unknown_unit(
        _request: Request, exc: UnknownUnitError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="UNKNOWN_UNIT",
            message=str(exc),
            details={"unit_id": exc.unit_id},
        )

    @application.exception_handler(ReservationNotFoundError)
    async def handle_reservation_not_found(
        _request: Request, exc: ReservationNotFoundError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="RESERVATION_NOT_FOUND",
            message=str(exc),
            details={"reservation_id": exc.reservation_id},
        )

    @application.exception_handler(InvalidRequesterError)
    async def handle_invalid_requester(
        _request: Request, exc: InvalidRequesterError
    ) -> JSONResponse:
        return _error_response(
            status_code=_HTTP_422,
            code="INVALID_REQUESTER",
            message=str(exc),
        )

    @application.exception_handler(InvalidTimeIntervalError)
    async def handle_invalid_interval(
        _request: Request, exc: InvalidTimeIntervalError
    ) -> JSONResponse:
        return _error_response(
            status_code=_HTTP_422,
            code="INVALID_TIME_INTERVAL",
            message=str(exc),
        )

    @application.exception_handler(ValidationDomainError)
    async def handle_validation_domain_error(
        _request: Request, exc: ValidationDomainError
    ) -> JSONResponse:
        return _error_response(
            status_code=_HTTP_422,
            code="DOMAIN_VALIDATION_ERROR",
            message=str(exc),
        )

    @application.exception_handler(ReservationOverlapError)
    async def handle_overlap(
        _request: Request, exc: ReservationOverlapError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="RESERVATION_OVERLAP",
            message=str(exc),
            details={
                "unit_id": exc.unit_id,
                "conflicting_reservation_ids": list(exc.conflicting_reservation_ids),
            },
        )

    @application.exception_handler(ReservationAlreadyCancelledError)
    async def handle_already_cancelled(
        _request: Request, exc: ReservationAlreadyCancelledError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="RESERVATION_ALREADY_CANCELLED",
            message=str(exc),
            details={"reservation_id": exc.reservation_id},
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        issues = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
            for err in exc.errors()
        ]
        return _error_response(
            status_code=_HTTP_422,
            code="REQUEST_VALIDATION_ERROR",
            message="Parámetros o cuerpo JSON de la solicitud inválidos.",
            details={"issues": issues},
        )

    @application.exception_handler(DataStorageError)
    async def handle_storage_error(
        _request: Request, exc: DataStorageError
    ) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATA_STORAGE_ERROR",
            message=str(exc),
        )

    @application.get("/units", response_model=list[UnitResponse])
    def list_units(
        service: ReservationService = Depends(get_reservation_service),
    ) -> list[UnitResponse]:
        """Lista las 5 unidades físicas precargadas del laboratorio (RF-01)."""
        return [UnitResponse.from_domain(unit) for unit in service.list_units()]

    @application.get("/availability", response_model=AvailabilityResponse)
    def check_availability(
        unit_id: str = Query(..., description="Identificador exacto de la unidad física."),
        start: str = Query(..., description="Inicio ISO local YYYY-MM-DDTHH:MM[:SS]."),
        end: str = Query(..., description="Fin ISO local YYYY-MM-DDTHH:MM[:SS]."),
        service: ReservationService = Depends(get_reservation_service),
    ) -> AvailabilityResponse:
        """Consulta disponibilidad aplicando idénticas reglas que la creación (RF-02, RN-07)."""
        result = service.check_availability(unit_id=unit_id, start=start, end=end)
        return AvailabilityResponse.from_domain(result)

    @application.post(
        "/reservations",
        response_model=ReservationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_reservation(
        payload: CreateReservationRequest,
        service: ReservationService = Depends(get_reservation_service),
    ) -> ReservationResponse:
        """Crea una nueva reserva activa si la unidad e intervalo están disponibles (RF-03)."""
        created = service.create_reservation(
            unit_id=payload.unit_id,
            requester=payload.requester,
            start=payload.start,
            end=payload.end,
        )
        return ReservationResponse.from_domain(created)

    @application.get("/reservations", response_model=list[ReservationResponse])
    def list_reservations(
        unit_id: str | None = Query(
            default=None, description="Filtra por ID exacto de unidad conocida."
        ),
        reservation_status: ReservationStatus | None = Query(
            default=None,
            alias="status",
            description="Filtra por estado ACTIVE o CANCELLED.",
        ),
        service: ReservationService = Depends(get_reservation_service),
    ) -> list[ReservationResponse]:
        """Lista el historial completo de reservas activas y canceladas (RF-05)."""
        items = service.list_reservations(unit_id=unit_id, status=reservation_status)
        return [ReservationResponse.from_domain(item) for item in items]

    @application.get(
        "/reservations/{reservation_id}", response_model=ReservationResponse
    )
    def get_reservation(
        reservation_id: str,
        service: ReservationService = Depends(get_reservation_service),
    ) -> ReservationResponse:
        """Recupera una reserva específica por su identificador único (RF-05)."""
        reservation = service.get_reservation(reservation_id)
        return ReservationResponse.from_domain(reservation)

    @application.post(
        "/reservations/{reservation_id}/cancel",
        response_model=ReservationResponse,
    )
    def cancel_reservation(
        reservation_id: str,
        service: ReservationService = Depends(get_reservation_service),
    ) -> ReservationResponse:
        """Cancela lógicamente una reserva conservando ID y datos y liberando el horario (RF-04)."""
        cancelled = service.cancel_reservation(reservation_id)
        return ReservationResponse.from_domain(cancelled)

    return application


# Punto de entrada directo para `uvicorn lab_reservations.api.app:app`
# (No toca disco al importarse; inicializa repositorios dentro del ciclo lifespan).
app = create_app()
