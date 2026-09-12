"""Prueba del orquestador con clientes falsos.

Lo que se verifica aqui es la decision de escalar: bajar el video cuesta tiempo,
ancho de banda y tokens, asi que solo debe pasar cuando el texto no alcanzo.
"""
from pathlib import Path

import pytest

from recipe_bot.config import Config
from recipe_bot.pipeline import run as run_mod
from recipe_bot.pipeline.run import Procesador
from recipe_bot.resolvers import Source
from tests.factories import receta


class ClienteFalso:
    """Devuelve una receta distinta por llamada y registra lo que recibio."""

    def __init__(self, recetas):
        self._recetas = list(recetas)
        self.llamadas = []
        self.messages = self

    def parse(self, **kwargs):
        self.llamadas.append(kwargs)
        salida = self._recetas.pop(0)
        return type("Resp", (), {"parsed_output": salida})()

    @property
    def imagenes_por_llamada(self):
        return [
            sum(1 for b in c["messages"][0]["content"] if b["type"] == "image")
            for c in self.llamadas
        ]


class ResolverFalso:
    nombre = "Falso"

    def __init__(self, source):
        self._source = source
        self.descargas = 0

    def matches(self, url):
        return True

    def resolve(self, url, workdir):
        return self._source

    def fetch_media(self, source, workdir):
        self.descargas += 1
        destino = workdir / "video.mp4"
        destino.write_bytes(b"fake")
        return destino


@pytest.fixture
def cfg(tmp_path):
    return Config(
        telegram_token="t", allowed_users=frozenset({1}),
        anthropic_model="claude-opus-5",
        airtable_token="a", airtable_base_id="appX", airtable_table="Recetas",
        airtable_base_atenea="appA", airtable_tabla_master="Master",
        airtable_tabla_sumandos="Sumandos",
        transcribe_base_url="https://x/v1", transcribe_api_key="", transcribe_model="whisper-1",
        work_dir=tmp_path, cookies_file=None, max_frames=16, frame_width=640,
    )


@pytest.fixture(autouse=True)
def sin_red_ni_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(run_mod, "guardar", lambda *a, **k: "https://airtable.com/appX/recY")

    def muestrear(video, workdir, max_cuadros, ancho):
        salida = workdir / "frames"
        salida.mkdir(parents=True, exist_ok=True)
        rutas = []
        for i in range(3):
            f = salida / f"frame_{i:03d}.jpg"
            f.write_bytes(b"\xff\xd8\xff")  # cabecera jpeg de mentiras
            rutas.append(f)
        return rutas

    monkeypatch.setattr(run_mod.frames_mod, "muestrear", muestrear)


def _procesar(cfg, cliente, source):
    p = Procesador(cfg, client=cliente)
    resolver = ResolverFalso(source)
    p.resolvers = [resolver]
    return p.desde_url("https://ejemplo.com/v"), resolver


CAPTION_COMPLETO = (
    "Huevos al albañil: 4 huevos, 200 g de jitomate picado, sal. "
    "Bate los huevos, sofríe el jitomate, mezcla y deja cuajar."
)


def test_caption_completo_resuelve_sin_bajar_el_video(cfg):
    cliente = ClienteFalso([receta(confianza="alta")])
    source = Source(plataforma="YouTube", url="u", caption=CAPTION_COMPLETO)

    resultado, resolver = _procesar(cfg, cliente, source)

    assert resultado.escalado is False
    assert resolver.descargas == 0
    assert len(cliente.llamadas) == 1
    assert cliente.imagenes_por_llamada == [0]


def test_confianza_baja_escala_a_video_y_cuadros(cfg):
    cliente = ClienteFalso([receta(confianza="baja"), receta(confianza="alta")])
    source = Source(plataforma="TikTok", url="u", caption=CAPTION_COMPLETO)

    resultado, resolver = _procesar(cfg, cliente, source)

    assert resultado.escalado is True
    assert resolver.descargas == 1
    assert cliente.imagenes_por_llamada == [0, 3]


def test_sin_caption_se_salta_la_pasada_barata(cfg):
    # Un reel de TikTok con musica y sin texto: la pasada de solo texto seria
    # una llamada tirada a la basura.
    cliente = ClienteFalso([receta(confianza="alta")])
    source = Source(plataforma="TikTok", url="u", caption="")

    resultado, resolver = _procesar(cfg, cliente, source)

    assert resultado.escalado is True
    assert resolver.descargas == 1
    assert cliente.imagenes_por_llamada == [3]


def test_video_muy_largo_no_se_baja_y_se_queda_con_lo_que_hay(cfg):
    cliente = ClienteFalso([receta(confianza="media")])
    source = Source(
        plataforma="YouTube", url="u", caption=CAPTION_COMPLETO,
        duracion_s=cfg.max_video_seconds + 1,
    )

    resultado, resolver = _procesar(cfg, cliente, source)

    assert resolver.descargas == 0
    assert resultado.escalado is False
    assert resultado.receta.confianza == "media"


def test_los_subtitulos_evitan_pagar_transcripcion(cfg):
    cliente = ClienteFalso([receta(confianza="baja"), receta(confianza="alta")])
    source = Source(
        plataforma="YouTube", url="u", caption="Huevos",
        subtitulos="Bate los huevos y sofríe el jitomate hasta que suelte el agua.",
    )

    p = Procesador(cfg, client=cliente)
    p.resolvers = [ResolverFalso(source)]
    p.desde_url("https://ejemplo.com/v")

    # _transcribir devuelve los subtitulos existentes sin tocar Whisper.
    assert p._transcribir(source, Path("/no/existe.mp4"), Path("/tmp")) == source.subtitulos


def test_la_carpeta_temporal_se_limpia_sola(cfg):
    cliente = ClienteFalso([receta(confianza="alta")])
    source = Source(plataforma="YouTube", url="u", caption=CAPTION_COMPLETO)
    _procesar(cfg, cliente, source)
    assert list(cfg.work_dir.iterdir()) == []


def test_el_archivo_subido_nunca_dispara_una_descarga(cfg, tmp_path):
    cliente = ClienteFalso([receta(confianza="alta")])
    video = tmp_path / "reel.mp4"
    video.write_bytes(b"fake")

    p = Procesador(cfg, client=cliente)
    resultado = p.desde_archivo(video, caption="")

    assert resultado.source.plataforma == "Archivo"
    assert resultado.source.url is None
    assert cliente.imagenes_por_llamada == [3]
