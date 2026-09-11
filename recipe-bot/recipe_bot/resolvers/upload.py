"""Archivo de video mandado directo al bot.

Es la red de seguridad del sistema: funciona igual para las cuatro plataformas
y no depende de ningun scraper que se pueda romper manana.
"""
from __future__ import annotations

from pathlib import Path

from .base import Source


def source_desde_archivo(ruta: Path, caption: str = "", duracion_s: int | None = None) -> Source:
    return Source(
        plataforma="Archivo",
        url=None,
        titulo=None,
        autor=None,
        caption=caption.strip(),
        subtitulos=None,
        duracion_s=duracion_s,
        media=ruta,
    )
