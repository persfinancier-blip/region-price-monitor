"""Panel app factory (ADR-0008: shell over `app/scripts/*`, no business logic)."""

from app.panel.app import create_app

__all__ = ["create_app"]
