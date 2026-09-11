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
