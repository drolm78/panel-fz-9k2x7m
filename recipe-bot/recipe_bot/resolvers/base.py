"""Contrato comun de los resolvedores + utilidades de yt-dlp compartidas."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


class ResolverError(RuntimeError):
    """Error que se le puede mostrar tal cual al usuario en Telegram."""


@dataclass
class Source:
    """Todo lo que logramos sacar de un video, antes de pasarselo al modelo.

    `caption` y `subtitulos` son la via barata; `media` es la cara (hay que
    bajar el video). El orquestador solo baja el video si la barata no alcanzo.
    """

    plataforma: str
    url: str | None = None
    titulo: str | None = None
    autor: str | None = None
    caption: str = ""
    subtitulos: str | None = None
    duracion_s: int | None = None
    media: Path | None = None
    extra: dict = field(default_factory=dict)

    @property
    def texto_barato(self) -> str:
        partes = [p for p in (self.titulo, self.caption, self.subtitulos) if p]
        return "\n\n".join(partes).strip()


@runtime_checkable
class Resolver(Protocol):
    nombre: str

    def matches(self, url: str) -> bool: ...

    def resolve(self, url: str, workdir: Path) -> Source: ...

    def fetch_media(self, source: Source, workdir: Path) -> Path | None: ...


# --- yt-dlp -----------------------------------------------------------------

_FORMATO = (
    "bv*[height<=720][ext=mp4]+ba[ext=m4a]/"
    "b[height<=720][ext=mp4]/b[ext=mp4]/b"
)


def _base_opts(cookies: Path | None) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
    }
    if cookies and cookies.exists():
        opts["cookiefile"] = str(cookies)
    return opts


def ytdlp_info(url: str, cookies: Path | None = None) -> dict:
    """Metadatos sin bajar nada."""
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL(_base_opts(cookies)) as ydl:
            return ydl.extract_info(url, download=False) or {}
    except Exception as exc:  # yt-dlp lanza de todo
        raise ResolverError(f"No pude leer el video: {exc}") from exc


def ytdlp_subtitles(
    url: str,
    workdir: Path,
    idiomas: tuple[str, ...] = ("es", "es-MX", "es-419", "en", "en-US"),
    cookies: Path | None = None,
) -> str | None:
    """Baja subtitulos (manuales o automaticos) y los devuelve como texto plano."""
    import yt_dlp

    from .vtt import vtt_a_texto

    opts = _base_opts(cookies) | {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": list(idiomas),
        "subtitlesformat": "vtt",
        "outtmpl": str(workdir / "sub.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as exc:
        log.info("sin subtitulos para %s: %s", url, exc)
        return None

    # yt-dlp escribe sub.<lang>.vtt; preferimos el primer idioma pedido que exista.
    archivos = sorted(workdir.glob("sub*.vtt"))
    if not archivos:
        return None
    for lang in idiomas:
        for f in archivos:
            if f".{lang.lower()}." in f.name.lower():
                return vtt_a_texto(f.read_text(encoding="utf-8", errors="replace"))
    return vtt_a_texto(archivos[0].read_text(encoding="utf-8", errors="replace"))


def ytdlp_video(url: str, workdir: Path, cookies: Path | None = None) -> Path:
    """Baja el video (<=720p) y devuelve la ruta del archivo."""
    import yt_dlp

    opts = _base_opts(cookies) | {
        "format": _FORMATO,
        "outtmpl": str(workdir / "video.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except Exception as exc:
        raise ResolverError(f"No pude bajar el video: {exc}") from exc

    for f in sorted(workdir.glob("video.*")):
        if f.is_file() and f.stat().st_size > 0:
            return f
    raise ResolverError("yt-dlp no dejo ningun archivo de video.")
