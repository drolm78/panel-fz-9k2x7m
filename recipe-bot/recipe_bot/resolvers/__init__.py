"""Registro de resolvedores: agregar una plataforma = agregar un archivo aqui."""
from __future__ import annotations

import re
from pathlib import Path

from .base import Resolver, ResolverError, Source
from .meta import MetaResolver
from .tiktok import TikTokResolver
from .upload import source_desde_archivo
from .youtube import YouTubeResolver

_URL_EN_TEXTO = re.compile(r"https?://\S+")

NO_SOPORTADA = (
    "No reconozco esa liga. Manejo YouTube, TikTok, Instagram y Facebook.\n\n"
    "Si es de otro lado, mandame el archivo de video y lo proceso igual."
)


def extraer_url(texto: str) -> str | None:
    """Saca la primera URL de un mensaje. Telegram suele mandar texto alrededor."""
    match = _URL_EN_TEXTO.search(texto or "")
    if not match:
        return None
    # Los links compartidos traen basura pegada al final con frecuencia.
    return match.group(0).rstrip(").,;\"'>")


def construir(cookies: Path | None = None) -> list[Resolver]:
    return [
        YouTubeResolver(cookies),
        TikTokResolver(cookies),
        MetaResolver(cookies),
    ]


def elegir(url: str, resolvers: list[Resolver]) -> Resolver:
    for r in resolvers:
        if r.matches(url):
            return r
    raise ResolverError(NO_SOPORTADA)


__all__ = [
    "Resolver",
    "ResolverError",
    "Source",
    "construir",
    "elegir",
    "extraer_url",
    "source_desde_archivo",
    "NO_SOPORTADA",
]
