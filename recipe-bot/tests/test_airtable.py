from datetime import date

from recipe_bot.models import Ingrediente
from recipe_bot.storage.airtable import construir_campos, formatear_ingredientes, formatear_pasos
from tests.factories import receta, source

HOY = date(2026, 9, 11)


def test_ingredientes_como_lista_legible():
    r = receta(ingredientes=[
        Ingrediente(cantidad="200 g", nombre="jitomate", nota="picado"),
        Ingrediente(cantidad=None, nombre="sal", nota=None),
    ])
    assert formatear_ingredientes(r) == "- 200 g jitomate (picado)\n- sal"


def test_pasos_van_numerados():
    assert formatear_pasos(receta(pasos=["Uno.", "Dos."])) == "1. Uno.\n2. Dos."


def test_campos_basicos():
    campos = construir_campos(receta(), source(), HOY)
    assert campos["Nombre"] == "Huevos al albañil"
    assert campos["Plataforma"] == "TikTok"
    assert campos["Keto"] is True
    assert campos["Tags"] == ["desayuno", "huevo"]
    assert campos["Agregada"] == "2026-09-11"
    assert campos["Carbos netos (g)"] == 6.5


def test_los_numericos_nulos_se_omiten_en_vez_de_mandar_null():
    # Airtable rechaza null en campos numericos con formato.
    campos = construir_campos(
        receta(porciones=None, kcal_porcion=None, proteina_g=None,
               carbos_netos_g=None, grasa_g=None, tiempo_min=None),
        source(), HOY,
    )
    for ausente in ("Porciones", "Tiempo (min)", "Kcal / porción",
                    "Proteína (g)", "Carbos netos (g)", "Grasa (g)"):
        assert ausente not in campos


def test_url_ausente_se_omite_en_archivos_subidos():
    campos = construir_campos(receta(), source(plataforma="Archivo", url=None), HOY)
    assert "URL" not in campos
    assert campos["Plataforma"] == "Archivo"


def test_lo_que_falto_queda_anotado_en_notas():
    campos = construir_campos(
        receta(falta=["cantidad de sal", "temperatura del horno"]), source(), HOY
    )
    assert "cantidad de sal; temperatura del horno" in campos["Notas"]


def test_notas_previas_se_conservan_junto_con_lo_faltante():
    campos = construir_campos(receta(notas="Sirve caliente.", falta=["porciones"]), source(), HOY)
    assert campos["Notas"].startswith("Sirve caliente.")
    assert "porciones" in campos["Notas"]
