"""Gastos: lo que importa es que no se inventen categorías ni se pierda contexto."""
from datetime import date

import pytest
from pydantic import ValidationError

from recipe_bot.models import CategoriaGasto, Gasto, LecturaGasto
from recipe_bot.storage.airtable import construir_campos_gasto
from recipe_bot.gastos import _dia_semana


def gasto(**overrides) -> Gasto:
    base = dict(
        concepto="gasolina", monto=350.0, fecha="2026-09-11",
        categoria="Transporte y viajes", ciudad="La Paz", tipo="Variable",
        forma_pago="Tarjeta crédito", deducible=True, notas=None,
        confianza="alta", falta=[],
    )
    base.update(overrides)
    return Gasto(**base)


def test_el_esquema_impide_categorias_inventadas():
    # La defensa no es el prompt: es que el tipo no admite otra cosa.
    with pytest.raises(ValidationError):
        gasto(categoria="Chunches varios")


def test_el_esquema_impide_formas_de_pago_inventadas():
    with pytest.raises(ValidationError):
        gasto(forma_pago="Bitcoin")


def test_las_doce_categorias_reales_si_pasan():
    for cat in CategoriaGasto.__args__:
        assert gasto(categoria=cat).categoria == cat


def test_campos_mapean_a_los_nombres_de_airtable():
    campos = construir_campos_gasto(gasto())
    assert campos["Concepto"] == "gasolina"
    assert campos["Monto"] == 350.0
    assert campos["Categoría"] == "Transporte y viajes"
    assert campos["Ciudad"] == "La Paz"
    assert campos["Tipo de gasto"] == "Variable"
    assert campos["Forma de pago"] == "Tarjeta crédito"
    assert campos["¿Deducible?"] is True
    assert campos["Fecha"] == "2026-09-11"


def test_lo_que_el_bot_supuso_queda_anotado_en_notas():
    # Si no dictaste la ciudad, tienes que poder verlo despues en Airtable.
    campos = construir_campos_gasto(gasto(falta=["ciudad", "forma de pago"]))
    assert "Supuesto por el bot: ciudad; forma de pago" in campos["Notas"]


def test_las_notas_dictadas_se_conservan_junto_con_lo_supuesto():
    campos = construir_campos_gasto(gasto(notas="Viaje a Balbuena", falta=["ciudad"]))
    assert campos["Notas"].startswith("Viaje a Balbuena")
    assert "ciudad" in campos["Notas"]


def test_un_mensaje_que_no_es_gasto_no_trae_gasto():
    lectura = LecturaGasto(es_gasto=False, gasto=None, respuesta="Eso parece una pregunta.")
    assert lectura.gasto is None
    assert lectura.respuesta


def test_dia_de_la_semana_en_espanol():
    assert _dia_semana(date(2026, 9, 11)) == "viernes"
    assert _dia_semana(date(2026, 9, 14)) == "lunes"
