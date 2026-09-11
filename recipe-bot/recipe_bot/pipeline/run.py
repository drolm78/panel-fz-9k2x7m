"""Orquestador: de una liga (o un archivo) a un registro en Airtable.

La idea central es escalar solo cuando hace falta. La primera pasada usa
unicamente texto (caption + subtitulos), que es gratis o casi. Si el modelo
reporta que quedo incompleta, entonces si bajamos el video, transcribimos y
muestreamos cuadros. En YouTube eso casi nunca ocurre; en TikTok casi siempre.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import anthropic

from ..config import Config
from ..models import Receta, necesita_escalar
from ..resolvers import Resolver, ResolverError, Source, construir, elegir, source_desde_archivo
from ..storage.airtable import guardar
from . import audio as audio_mod
from . import frames as frames_mod
from .extract import extraer

log = logging.getLogger(__name__)

MIN_TEXTO_UTIL = 40


@dataclass
class Resultado:
    receta: Receta
    source: Source
    airtable_url: str
    escalado: bool


class Procesador:
    def __init__(self, cfg: Config, client: anthropic.Anthropic | None = None) -> None:
        self.cfg = cfg
        self.client = client or anthropic.Anthropic()
        self.resolvers: list[Resolver] = construir(cfg.cookies_file)
        cfg.work_dir.mkdir(parents=True, exist_ok=True)

    # -- entradas ----------------------------------------------------------

    def desde_url(self, url: str) -> Resultado:
        with self._workdir() as wd:
            resolver = elegir(url, self.resolvers)
            source = resolver.resolve(url, wd)
            return self._procesar(source, wd, resolver)

    def desde_archivo(self, ruta: Path, caption: str = "") -> Resultado:
        with self._workdir() as wd:
            destino = wd / ruta.name
            if ruta.resolve() != destino.resolve():
                shutil.copy2(ruta, destino)
            return self._procesar(source_desde_archivo(destino, caption), wd, None)

    # -- nucleo ------------------------------------------------------------

    def _procesar(self, source: Source, wd: Path, resolver: Resolver | None) -> Resultado:
        receta = None
        escalado = False

        # Pasada 1: solo texto. Se salta si no hay practicamente nada que leer.
        if len(source.texto_barato) >= MIN_TEXTO_UTIL:
            receta = extraer(self.client, self.cfg.anthropic_model, source)
            if not necesita_escalar(receta):
                log.info("resuelto con texto; no bajo el video")
                return self._guardar(receta, source, escalado)
            log.info("texto insuficiente (confianza=%s); escalo", receta.confianza)
        else:
            log.info("sin texto util; voy directo al video")

        # Pasada 2: el video completo.
        media = self._asegurar_media(source, wd, resolver)
        if media is None:
            if receta is not None:
                return self._guardar(receta, source, escalado)
            raise ResolverError(
                "No pude obtener el video ni encontré texto suficiente para sacar la receta."
            )

        escalado = True
        transcripcion = self._transcribir(source, media, wd)
        cuadros = self._cuadros(media, wd)
        receta = extraer(
            self.client, self.cfg.anthropic_model, source, transcripcion, cuadros
        )
        return self._guardar(receta, source, escalado)

    def _asegurar_media(self, source: Source, wd: Path, resolver: Resolver | None) -> Path | None:
        if source.media and source.media.exists():
            return source.media
        if resolver is None:
            return None
        if source.duracion_s and source.duracion_s > self.cfg.max_video_seconds:
            log.info("video de %ss: muy largo para bajarlo", source.duracion_s)
            return None
        media = resolver.fetch_media(source, wd)
        source.media = media
        return media

    def _transcribir(self, source: Source, media: Path, wd: Path) -> str | None:
        if source.subtitulos:
            # Ya tenemos texto del audio por la via gratis; Whisper no aporta.
            return source.subtitulos
        if not self.cfg.can_transcribe:
            log.info("sin TRANSCRIBE_API_KEY: me quedo con los cuadros")
            return None
        try:
            return audio_mod.transcribir(
                audio_mod.extraer_audio(media, wd),
                self.cfg.transcribe_base_url,
                self.cfg.transcribe_api_key,
                self.cfg.transcribe_model,
            )
        except audio_mod.TranscripcionError as exc:
            # Un reel con pura música no tiene por qué tumbar todo el proceso:
            # los cuadros suelen bastar.
            log.warning("no pude transcribir: %s", exc)
            return None

    def _cuadros(self, media: Path, wd: Path) -> list[Path]:
        try:
            return frames_mod.muestrear(media, wd, self.cfg.max_frames, self.cfg.frame_width)
        except frames_mod.FFmpegNoDisponible:
            raise
        except Exception as exc:
            log.warning("no pude muestrear cuadros: %s", exc)
            return []

    def _guardar(self, receta: Receta, source: Source, escalado: bool) -> Resultado:
        url = guardar(
            receta,
            source,
            self.cfg.airtable_token,
            self.cfg.airtable_base_id,
            self.cfg.airtable_table,
        )
        return Resultado(receta=receta, source=source, airtable_url=url, escalado=escalado)

    @contextmanager
    def _workdir(self):
        """Carpeta temporal que se borra sola: los videos pesan y se acumulan."""
        with tempfile.TemporaryDirectory(dir=self.cfg.work_dir) as nombre:
            yield Path(nombre)
