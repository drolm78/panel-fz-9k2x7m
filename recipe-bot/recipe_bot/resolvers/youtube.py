"""YouTube: la plataforma facil. Descripcion + subtitulos suelen bastar."""
from __future__ import annotations

import re
from pathlib import Path

from .base import Resolver, Source, ytdlp_info, ytdlp_subtitles, ytdlp_video

_URL = re.compile(r"(youtube\.com|youtu\.be)", re.I)


class YouTubeResolver(Resolver):
    nombre = "YouTube"

    def __init__(self, cookies: Path | None = None) -> None:
        self.cookies = cookies

    def matches(self, url: str) -> bool:
        return bool(_URL.search(url))

    def resolve(self, url: str, workdir: Path) -> Source:
        info = ytdlp_info(url, self.cookies)
        return Source(
            plataforma=self.nombre,
            url=info.get("webpage_url") or url,
            titulo=info.get("title"),
            autor=info.get("uploader") or info.get("channel"),
            # Muchisimos canales de cocina ponen la receta completa en la
            # descripcion: es la fuente mas barata y mas exacta que existe.
            caption=(info.get("description") or "").strip(),
            subtitulos=ytdlp_subtitles(url, workdir, cookies=self.cookies),
            duracion_s=info.get("duration"),
        )

    def fetch_media(self, source: Source, workdir: Path) -> Path | None:
        if not source.url:
            return None
        return ytdlp_video(source.url, workdir, self.cookies)
