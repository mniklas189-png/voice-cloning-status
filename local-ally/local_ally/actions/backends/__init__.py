"""Plattformabhaengige Umsetzung der Aktionen."""

from .base import NotSupported, SystemBackend, create_backend

__all__ = ["NotSupported", "SystemBackend", "create_backend"]
