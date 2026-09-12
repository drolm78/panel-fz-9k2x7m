from recipe_bot.bot import _archivo_del_mensaje, formatear
from recipe_bot.pipeline.run import Resultado
from tests.factories import receta, source


def _resultado(**kw):
    return Resultado(
        receta=receta(**kw), source=source(),
        airtable_url="https://airtable.com/appX/recY", escalado=False,
    )


def test_el_mensaje_trae_titulo_ingredientes_pasos_y_liga():
    texto = formatear(_resultado())
    assert "<b>Huevos al albañil</b>" in texto
    assert "• 200 g jitomate (picado)" in texto
    assert "1. Bate los huevos." in texto
    assert 'href="https://airtable.com/appX/recY"' in texto


def test_escapa_html_del_contenido_para_no_romper_el_parseo():
    texto = formatear(_resultado(titulo="Pan <con> & queso"))
    assert "Pan &lt;con&gt; &amp; queso" in texto
    assert "<con>" not in texto


def test_muestra_la_adaptacion_keto_solo_cuando_no_es_keto():
    con = formatear(_resultado(es_keto=False, adaptacion_keto="Cambia la tortilla por hoja verde."))
    assert "Para keto:" in con
    sin = formatear(_resultado(es_keto=True, adaptacion_keto="lo que sea"))
    assert "Para keto:" not in sin


def test_avisa_cuando_la_receta_quedo_incompleta():
    assert "Quedó incompleto" in formatear(_resultado(falta=["cantidad de sal"]))


def test_macros_omiten_los_campos_nulos():
    texto = formatear(_resultado(proteina_g=None, grasa_g=None))
    linea = next(l for l in texto.splitlines() if "por porción" in l)
    assert "310 kcal" in linea and "C netos 6.5 g" in linea
    assert "P " not in linea and "G " not in linea


def test_reconoce_el_video_en_sus_distintos_campos():
    assert _archivo_del_mensaje({"video": {"file_id": "a"}})["file_id"] == "a"
    assert _archivo_del_mensaje({"video_note": {"file_id": "b"}})["file_id"] == "b"
    assert _archivo_del_mensaje({"animation": {"file_id": "c"}})["file_id"] == "c"


def test_documento_de_video_si_cuenta_pero_un_pdf_no():
    assert _archivo_del_mensaje({"document": {"file_id": "d", "mime_type": "video/mp4"}})
    assert _archivo_del_mensaje({"document": {"file_id": "e", "mime_type": "application/pdf"}}) is None
    assert _archivo_del_mensaje({"text": "hola"}) is None


# --- movimientos de Atenea y notas de voz ---------------------------------

from recipe_bot.atenea import Catalogo  # noqa: E402
from recipe_bot.bot import _voz_del_mensaje, formatear_movimiento  # noqa: E402
from recipe_bot.models import LecturaMovimiento, Movimiento  # noqa: E402
from recipe_bot.pipeline.run import ResultadoMovimiento  # noqa: E402
from recipe_bot.storage.airtable import resolver  # noqa: E402

CATALOGO = Catalogo(
    formas_pago={"Inbursa": "recINB"},
    lugares=("Walmart", "Gasolinera"),
    categorias=("Súper", "Comida"),
)


def _mov(**kw):
    base = dict(
        fecha="2026-09-11", monto=500.0, forma_pago="Inbursa", lugar="Walmart",
        categoria="Súper", detalles=None, confianza="alta", falta=[],
    )
    base.update(kw)
    m = Movimiento(**base)
    return ResultadoMovimiento(
        lectura=LecturaMovimiento(es_movimiento=True, movimiento=m, respuesta=None),
        resuelto=resolver(m, CATALOGO),
        airtable_url="https://airtable.com/appA/recM",
    )


def test_el_movimiento_muestra_monto_lugar_categoria_y_cuenta():
    texto = formatear_movimiento(_mov())
    assert "<b>$500.00</b>" in texto
    assert "Walmart" in texto
    assert "Súper · Inbursa · 2026-09-11" in texto
    assert 'href="https://airtable.com/appA/recM"' in texto


def test_los_montos_grandes_llevan_separador_de_miles():
    assert "$12,450.00" in formatear_movimiento(_mov(monto=12450.0))


def test_avisa_lo_que_no_esta_en_el_catalogo():
    texto = formatear_movimiento(_mov(lugar="Tienda X"))
    assert "No están en tu catálogo" in texto
    assert "sin lugar" in texto


def test_escapa_html_del_contenido():
    texto = formatear_movimiento(_mov(detalles="Pan <con> & queso"))
    assert "Pan &lt;con&gt; &amp; queso" in texto


def test_si_no_era_movimiento_devuelve_la_explicacion_del_modelo():
    r = ResultadoMovimiento(
        lectura=LecturaMovimiento(es_movimiento=False, movimiento=None,
                                  respuesta="Entendí una pregunta, no un gasto."),
        resuelto=None, airtable_url=None,
    )
    assert formatear_movimiento(r) == "Entendí una pregunta, no un gasto."


def test_reconoce_la_nota_de_voz_y_el_audio():
    assert _voz_del_mensaje({"voice": {"file_id": "a"}})["file_id"] == "a"
    assert _voz_del_mensaje({"audio": {"file_id": "b"}})["file_id"] == "b"
    assert _voz_del_mensaje({"document": {"file_id": "c", "mime_type": "audio/ogg"}})


def test_un_video_no_se_confunde_con_una_nota_de_voz():
    assert _voz_del_mensaje({"video": {"file_id": "v"}}) is None
    assert _archivo_del_mensaje({"voice": {"file_id": "a"}}) is None


# --- recetas médicas -------------------------------------------------------

from datetime import date as _date  # noqa: E402

from recipe_bot.bot import formatear_receta  # noqa: E402
from recipe_bot.consulta import CatalogoClinico, Paciente  # noqa: E402
from recipe_bot.models import LecturaReceta  # noqa: E402
from recipe_bot.pipeline.run import ResultadoReceta  # noqa: E402
from recipe_bot.storage.airtable import resolver_receta  # noqa: E402

_MED = "Tradea LP Tabletas 20 mg. Caja con 30 tabletas. (Metilfenidato liberación prolongada)"
_CAT = CatalogoClinico(
    pacientes=(Paciente("Juan Pérez López", "recJUAN"), Paciente("Ana Gómez Ruiz", "recANA")),
    medicamentos=(_MED,), presentaciones=("Una caja con 30 tabletas",),
)


def _receta(guardada=True, **kw):
    base = dict(
        es_receta=True, paciente="Juan Pérez", medicamento=_MED,
        indicacion="Tomar una tableta por la mañana durante 30 días.",
        presentacion="Una caja con 30 tabletas", repetir_dias=None,
        repetir_meses=None, respuesta=None,
    )
    base.update(kw)
    lec = LecturaReceta(**base)
    res = resolver_receta(lec, _CAT, _date(2026, 9, 12))
    return ResultadoReceta(
        lectura=lec, resuelta=res,
        airtable_url="https://airtable.com/appC/recN" if guardada and not res.ambigua else None,
    )


def test_la_receta_muestra_paciente_medicamento_e_indicacion():
    texto = formatear_receta(_receta())
    assert "<b>Juan Pérez López</b>" in texto
    assert "Tradea LP Tabletas 20 mg" in texto
    assert "Tomar una tableta por la mañana" in texto
    assert "Nota del 2026-09-12" in texto


def test_avisa_la_fecha_de_la_siguiente_receta():
    assert "Siguiente receta: <b>2026-10-12</b>" in formatear_receta(_receta(repetir_meses=1))


def test_cuando_el_paciente_es_ambiguo_lo_dice_y_no_guarda():
    texto = formatear_receta(_receta(paciente="Rodrigo Villanueva"))
    assert "No guardé nada" in texto
    assert "¿Es alguno de estos?" in texto
    assert "Juan Pérez López" in texto  # los candidatos, para que elija
    assert "Ver la nota" not in texto   # sin liga: no hay registro


def test_un_medicamento_fuera_del_catalogo_se_reporta():
    texto = formatear_receta(_receta(medicamento="Tradea 200 mg"))
    assert "No están en tu catálogo" in texto
    assert "sin medicamento" in texto


def test_escapa_html_de_los_nombres():
    r = _receta()
    r.resuelta.lectura.indicacion = "Tomar <1> tableta & media"
    assert "&lt;1&gt; tableta &amp; media" in formatear_receta(r)
