"""API pública de la capa HTTP REST (FastAPI)."""

from lab_reservations.api.app import app, create_app

__all__ = ["app", "create_app"]
