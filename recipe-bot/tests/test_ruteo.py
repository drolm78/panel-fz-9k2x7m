"""El bot ahora hace dos cosas: hay que probar que manda cada mensaje a la correcta."""
import pytest

from recipe_bot import bot as bot_mod
from recipe_bot.atenea import Catalogo
from recipe_bot.config import Config
from recipe_bot.models import LecturaMovimiento, Movimiento
from recipe_bot.pipeline.run import ResultadoMovimiento
from recipe_bot.storage.airtable import resolver

CATALOGO = Catalogo(formas_pago={"Inbursa": "recINB"}, lugares=("Gasolinera",),
                    categorias=("Carro",))


def _resultado_movimiento():
    m = Movimiento(fecha="2026-09-11", monto=350.0, forma_pago="Inbursa",
                   lugar="Gasolinera", categoria="Carro", detalles=None,
                   confianza="alta", falta=[])
    return ResultadoMovimiento(
        lectura=LecturaMovimiento(es_movimiento=True, movimiento=m, respuesta=None),
        resuelto=resolver(m, CATALOGO),
        airtable_url="https://airtable.com/appA/recM",
    )


@pytest.fixture
def cfg(tmp_path):
    return Config(
        telegram_token="t", allowed_users=frozenset({7}),
        anthropic_model="claude-opus-5",
        airtable_token="a", airtable_base_id="appX", airtable_table="Recetas",
        airtable_base_atenea="appA", airtable_tabla_master="Master",
        airtable_tabla_sumandos="Sumandos",
        transcribe_base_url="https://x/v1", transcribe_api_key="k", transcribe_model="w",
        work_dir=tmp_path, cookies_file=None, max_frames=16, frame_width=640,
    )


class TelegramFalso:
    def __init__(self, *a, **k):
        self.enviados = []

    def enviar(self, chat_id, texto, html_mode=False):
        self.enviados.append(texto)

    def descargar(self, file_id, destino):
        ruta = destino / "voz.oga"
        ruta.write_bytes(b"fake")
        return ruta


class ProcesadorFalso:
    def __init__(self, *a, **k):
        self.llamadas = []
        self.transcripcion = "350 de gasolina"

    def desde_url(self, url):
        self.llamadas.append(("video", url))
        return "RESULTADO_VIDEO"

    def movimiento_desde_texto(self, texto):
        self.llamadas.append(("gasto", texto))
        return _resultado_movimiento()

    def transcribir_archivo(self, ruta):
        self.llamadas.append(("transcribir", ruta.name))
        return self.transcripcion


@pytest.fixture
def armado(cfg, monkeypatch):
    monkeypatch.setattr(bot_mod, "Telegram", TelegramFalso)
    monkeypatch.setattr(bot_mod, "Procesador", ProcesadorFalso)
    monkeypatch.setattr(bot_mod, "formatear", lambda r: f"receta:{r}")
    b = bot_mod.Bot(cfg)
    return b


def _mensaje(**kw):
    return {"message": {"chat": {"id": 1}, "from": {"id": 7}, **kw}}


def test_un_mensaje_con_liga_va_al_camino_de_video(armado):
    armado._manejar(_mensaje(text="https://youtu.be/abc"))
    assert ("video", "https://youtu.be/abc") in armado.procesador.llamadas
    assert not any(c[0] == "gasto" for c in armado.procesador.llamadas)


def test_un_mensaje_sin_liga_va_al_camino_de_gasto(armado):
    armado._manejar(_mensaje(text="350 de gasolina, tarjeta, ayer"))
    assert ("gasto", "350 de gasolina, tarjeta, ayer") in armado.procesador.llamadas
    assert not any(c[0] == "video" for c in armado.procesador.llamadas)


def test_el_gasto_se_responde_formateado_y_sin_errores(armado):
    armado._manejar(_mensaje(text="350 de gasolina"))
    respuesta = armado.tg.enviados[-1]
    assert "$350.00" in respuesta and "Gasolinera" in respuesta
    assert not any(t.startswith("Se atoró") for t in armado.tg.enviados)


def test_una_nota_de_voz_se_transcribe_y_luego_se_rutea(armado):
    armado._manejar(_mensaje(voice={"file_id": "v1", "file_size": 1000}))
    tipos = [c[0] for c in armado.procesador.llamadas]
    assert tipos == ["transcribir", "gasto"]


def test_la_transcripcion_se_muestra_antes_de_actuar(armado):
    # Con dictado tienes que poder ver qué entendió antes de confiar en el registro.
    armado._manejar(_mensaje(voice={"file_id": "v1", "file_size": 1000}))
    assert any(t.startswith("🎙 «350 de gasolina»") for t in armado.tg.enviados)


def test_una_nota_de_voz_con_liga_dictada_va_a_video(armado):
    armado.procesador.transcripcion = "mira esta receta https://youtu.be/xyz"
    armado._manejar(_mensaje(voice={"file_id": "v1", "file_size": 1000}))
    assert ("video", "https://youtu.be/xyz") in armado.procesador.llamadas


def test_una_nota_de_voz_vacia_no_dispara_nada(armado):
    armado.procesador.transcripcion = "   "
    armado._manejar(_mensaje(voice={"file_id": "v1", "file_size": 1000}))
    assert [c[0] for c in armado.procesador.llamadas] == ["transcribir"]


def test_start_contesta_la_ayuda_sin_tocar_el_procesador(armado):
    armado._manejar(_mensaje(text="/start"))
    assert armado.procesador.llamadas == []
    assert "GASTOS" in armado.tg.enviados[0]


def test_un_usuario_ajeno_se_ignora_por_completo(armado):
    armado._manejar({"message": {"chat": {"id": 1}, "from": {"id": 999}, "text": "500 de algo"}})
    assert armado.procesador.llamadas == []
    assert armado.tg.enviados == []


def test_sin_base_de_gastos_configurada_lo_dice_en_vez_de_fallar(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(bot_mod, "Telegram", TelegramFalso)
    monkeypatch.setattr(bot_mod, "Procesador", ProcesadorFalso)
    sin_gastos = Config(**{**cfg.__dict__, "airtable_base_atenea": ""})
    b = bot_mod.Bot(sin_gastos)
    b._manejar(_mensaje(text="350 de gasolina"))
    assert b.procesador.llamadas == []
    assert "AIRTABLE_BASE_ATENEA" in b.tg.enviados[0]
