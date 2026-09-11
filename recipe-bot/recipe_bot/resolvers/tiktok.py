"""TikTok.

Dos particularidades frente a YouTube:

1. Tiene oEmbed publico y sin autenticacion, y el campo `title` que devuelve es
   en realidad el caption completo del post. Gratis y estable: se intenta
   primero, antes que yt-dlp.
2. El audio suele ser musica, no narracion. Aqui el analisis de cuadros no es
   un complemento sino el canal principal, asi que casi siempre escalamos.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import requests

from .base import Resolver, Source, ytdlp_info, ytdlp_video

log = logging.getLogger(__name__)

_URL = re.compile(r"(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)", re.I)
_OEMBED = "https://www.tiktok.com/oembed"


def oembed(url: str, timeout: float = 10.0) -> dict:
    try:
        r = requests.get(_OEMBED, params={"url": url}, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        log.info("oembed de tiktok respondio %s", r.status_code)
    except Exception as exc:
        log.info("oembed de tiktok fallo: %s", exc)
    return {}


class TikTokResolver(Resolver):
    nombre = "TikTok"

    def __init__(self, cookies: Path | None = None) -> None:
        self.cookies = cookies

    def matches(self, url: str) -> bool:
        return bool(_URL.search(url))

    def resolve(self, url: str, workdir: Path) -> Source:
        meta = oembed(url)
        caption = (meta.get("title") or "").strip()
        autor = meta.get("author_name")
        duracion = None

        if not caption:
            # oEmbed no dio nada (post privado, link acortado raro): plan B.
            info = ytdlp_info(url, self.cookies)
            caption = (info.get("description") or "").strip()
            autor = autor or info.get("uploader")
            duracion = info.get("duration")

        return Source(
            plataforma=self.nombre,
            url=url,
            titulo=None,
            autor=autor,
            caption=caption,
            subtitulos=None,
            duracion_s=duracion,
        )

    def fetch_media(self, source: Source, workdir: Path) -> Path | None:
        if not source.url:
            return None
        return ytdlp_video(source.url, workdir, self.cookies)
