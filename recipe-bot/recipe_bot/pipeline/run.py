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
from .. import router
from ..atenea import Catalogo, cargar_catalogo
from ..atenea import leer as leer_movimiento
from ..consulta import CatalogoClinico
from ..consulta import cargar_catalogo as cargar_catalogo_clinico
from ..consulta import leer as leer_receta
from ..models import Intencion, LecturaMovimiento, LecturaReceta, Receta, necesita_escalar
from ..resolvers import Resolver, ResolverError, Source, construir, elegir, source_desde_archivo
from ..storage.airtable import (MovimientoResuelto, RecetaResuelta, guardar,
                                guardar_movimiento, guardar_receta, resolver,
                                resolver_receta)
from . import audio as audio_mod
from . import frames as frames_mod
from .extract import extraer

log = logging.getLogger(__name__)

MIN_TEXTO_UTIL = 40


@dataclass
class ResultadoMovimiento:
    lectura: LecturaMovimiento
    resuelto: MovimientoResuelto | None
    airtable_url: str | None


@dataclass
class ResultadoReceta:
    lectura: LecturaReceta
    resuelta: RecetaResuelta | None
    airtable_url: str | None


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
        self._catalogo: Catalogo | None = None
        self._catalogo_clinico: CatalogoClinico | None = None
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

    def catalogo_atenea(self) -> Catalogo:
        """Catálogo vivo de Airtable, cacheado 10 min para no pedirlo en cada gasto."""
        if self._catalogo is None or not self._catalogo.vigente:
            self._catalogo = cargar_catalogo(
                self.cfg.airtable_token,
                self.cfg.airtable_base_atenea,
                self.cfg.airtable_tabla_master,
                self.cfg.airtable_tabla_sumandos,
            )
        return self._catalogo

    def clasificar(self, texto: str) -> Intencion:
        return router.clasificar(self.client, self.cfg.anthropic_model, texto)

    def catalogo_clinico(self) -> CatalogoClinico:
        """3166 pacientes: se traen una vez y se guardan una hora."""
        if self._catalogo_clinico is None or not self._catalogo_clinico.vigente:
            self._catalogo_clinico = cargar_catalogo_clinico(
                self.cfg.airtable_token,
                self.cfg.airtable_base_consulta,
                self.cfg.airtable_tabla_notas,
                self.cfg.airtable_tabla_pacientes,
                "Nombre del paciente",
            )
        return self._catalogo_clinico

    def receta_desde_texto(self, texto: str) -> ResultadoReceta:
        """Si el paciente no queda claro, NO escribe nada: devuelve los candidatos."""
        catalogo = self.catalogo_clinico()
        lectura = leer_receta(self.client, self.cfg.anthropic_model, texto, catalogo)
        if not lectura.es_receta:
            return ResultadoReceta(lectura=lectura, resuelta=None, airtable_url=None)

        resuelta = resolver_receta(lectura, catalogo)
        if resuelta.ambigua:
            return ResultadoReceta(lectura=lectura, resuelta=resuelta, airtable_url=None)

        url = guardar_receta(
            resuelta,
            self.cfg.airtable_token,
            self.cfg.airtable_base_consulta,
            self.cfg.airtable_tabla_notas,
        )
        return ResultadoReceta(lectura=lectura, resuelta=resuelta, airtable_url=url)

    def movimiento_desde_texto(self, texto: str) -> ResultadoMovimiento:
        """Lee un movimiento dictado. Si no era un movimiento, no guarda nada."""
        catalogo = self.catalogo_atenea()
        lectura = leer_movimiento(self.client, self.cfg.anthropic_model, texto, catalogo)
        if not lectura.es_movimiento or lectura.movimiento is None:
            return ResultadoMovimiento(lectura=lectura, resuelto=None, airtable_url=None)

        resuelto = resolver(lectura.movimiento, catalogo)
        url = guardar_movimiento(
            resuelto,
            self.cfg.airtable_token,
            self.cfg.airtable_base_atenea,
            self.cfg.airtable_tabla_master,
        )
        return ResultadoMovimiento(lectura=lectura, resuelto=resuelto, airtable_url=url)

    def transcribir_archivo(self, audio: Path) -> str:
        """Nota de voz -> texto. Whisper acepta el .oga de Telegram tal cual."""
        if not self.cfg.can_transcribe:
            raise ResolverError(
                "Para las notas de voz necesito TRANSCRIBE_API_KEY en el .env."
            )
        return audio_mod.transcribir(
            audio,
            self.cfg.transcribe_base_url,
            self.cfg.transcribe_api_key,
            self.cfg.transcribe_model,
        )

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
