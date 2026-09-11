"""Instagram y Facebook.

Son el mismo backend y el mismo problema: no hay API publica para contenido
ajeno, y sin sesion iniciada yt-dlp choca contra el muro de login. Por eso el
error de este resolvedor no es un error tecnico sino una instruccion: comparte
el archivo de video en vez del link y el resto del pipeline funciona igual.
"""
from __future__ import annotations

import re
from pathlib import Path

from .base import Resolver, ResolverError, Source, ytdlp_info, ytdlp_video

_URL = re.compile(r"(instagram\.com|facebook\.com|fb\.watch|fb\.com)", re.I)

AYUDA = (
    "No pude leer ese link (Instagram y Facebook bloquean el acceso sin sesion).\n\n"
    "Abre el video, dale Compartir y mandamelo como ARCHIVO DE VIDEO en vez "
    "del link. Asi lo proceso igual y sin depender de scraping."
)


class MetaResolver(Resolver):
    nombre = "Meta"

    def __init__(self, cookies: Path | None = None) -> None:
        self.cookies = cookies

    def matches(self, url: str) -> bool:
        return bool(_URL.search(url))

    def _plataforma(self, url: str) -> str:
        return "Instagram" if "instagram.com" in url.lower() else "Facebook"

    def resolve(self, url: str, workdir: Path) -> Source:
        try:
            info = ytdlp_info(url, self.cookies)
        except ResolverError as exc:
            raise ResolverError(AYUDA) from exc

        return Source(
            plataforma=self._plataforma(url),
            url=info.get("webpage_url") or url,
            titulo=info.get("title"),
            autor=info.get("uploader"),
            # En Facebook mucha receta vive en el texto del post, igual que en
            # las descripciones de YouTube.
            caption=(info.get("description") or "").strip(),
            subtitulos=None,
            duracion_s=info.get("duration"),
        )

    def fetch_media(self, source: Source, workdir: Path) -> Path | None:
        if not source.url:
            return None
        try:
            return ytdlp_video(source.url, workdir, self.cookies)
        except ResolverError as exc:
            raise ResolverError(AYUDA) from exc
