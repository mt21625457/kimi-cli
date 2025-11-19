"""Kimi HTTP service package."""

from __future__ import annotations

from importlib import metadata

try:  # pragma: no cover - fallback when package metadata is unavailable
    __version__ = metadata.version("kimi-cli")
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
