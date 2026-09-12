"""Recetas: la prueba que más importa es que NUNCA escriba en el expediente equivocado."""
from datetime import date

import pytest

from recipe_bot.consulta import CatalogoClinico, Paciente, hay_ganador, sumar_meses
from recipe_bot.models import LecturaReceta
from recipe_bot.storage.airtable import (AirtableError, construir_campos_receta,
                                         resolver_receta)

HOY = date(2026, 9, 12)

MEDICAMENTO = "Tradea LP Tabletas 20 mg. Caja con 30 tabletas. (Metilfenidato liberación prolongada)"
PRESENTACION = "Una caja con 30 tabletas"


@pytest.fixture
def catalogo():
    return CatalogoClinico(
        pacientes=(
            Paciente("Juan Pérez López", "recJUAN"),
            Paciente("Ana Gómez Ruiz", "recANA"),
            Paciente("María Fernanda Solís", "recMARIA"),
        ),
        medicamentos=(MEDICAMENTO, "Sertralina tabletas 50 mg. Caja con 14 o 28 tabletas."),
        presentaciones=(PRESENTACION, "Un frasco con 10 ml"),
    )


def lectura(**kw) -> LecturaReceta:
    base = dict(
        es_receta=True, paciente="Juan Pérez", medicamento=MEDICAMENTO,
        indicacion="Tomar una tableta por la mañana durante 30 días.",
        presentacion=PRESENTACION, repetir_dias=None, repetir_meses=None, respuesta=None,
    )
    base.update(kw)
    return LecturaReceta(**base)


# --- aritmética de fechas --------------------------------------------------

def test_dentro_de_un_mes_es_el_mismo_dia_del_mes_siguiente():
    assert sumar_meses(date(2026, 9, 12), 1) == date(2026, 10, 12)


def test_el_31_mas_un_mes_no_se_desborda_al_mes_siguiente():
    # 31 de enero + 1 mes es 28 de febrero, no 3 de marzo.
    assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_año_bisiesto():
    assert sumar_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_cruza_el_año():
    assert sumar_meses(date(2026, 11, 30), 2) == date(2027, 1, 30)


def test_date2_se_llena_con_meses(catalogo):
    r = resolver_receta(lectura(repetir_meses=1), catalogo, HOY)
    assert r.date2 == date(2026, 10, 12)


def test_date2_se_llena_con_dias(catalogo):
    r = resolver_receta(lectura(repetir_dias=15), catalogo, HOY)
    assert r.date2 == date(2026, 9, 27)


def test_sin_repeticion_no_hay_date2(catalogo):
    assert resolver_receta(lectura(), catalogo, HOY).date2 is None
    assert "Date2" not in construir_campos_receta(resolver_receta(lectura(), catalogo, HOY))


# --- identificación del paciente -------------------------------------------

def test_encuentra_al_paciente_con_el_nombre_incompleto(catalogo):
    r = resolver_receta(lectura(paciente="Juan Pérez"), catalogo, HOY)
    assert r.paciente.record_id == "recJUAN"


def test_encuentra_al_paciente_aunque_whisper_le_quite_los_acentos(catalogo):
    r = resolver_receta(lectura(paciente="juan perez lopez"), catalogo, HOY)
    assert r.paciente.record_id == "recJUAN"


def test_un_nombre_que_no_se_parece_a_nadie_no_se_asigna(catalogo):
    r = resolver_receta(lectura(paciente="Rodrigo Villanueva"), catalogo, HOY)
    assert r.ambigua
    assert r.paciente is None


def test_ante_dos_pacientes_igual_de_parecidos_no_elige(catalogo):
    gemelos = CatalogoClinico(
        pacientes=(Paciente("Luis García Mora", "recA"), Paciente("Luis García Mota", "recB")),
        medicamentos=(), presentaciones=(),
    )
    assert hay_ganador(gemelos.buscar_pacientes("Luis García Mo")) is None


def test_una_receta_ambigua_no_se_puede_escribir(catalogo):
    r = resolver_receta(lectura(paciente="Nadie Conocido"), catalogo, HOY)
    with pytest.raises(AirtableError, match="sin paciente resuelto"):
        construir_campos_receta(r)


# --- campos que se mandan a Airtable ---------------------------------------

def test_la_receta_completa_llena_los_campos_esperados(catalogo):
    campos = construir_campos_receta(resolver_receta(lectura(repetir_meses=1), catalogo, HOY))
    assert campos["Paciente"] == ["recJUAN"]          # lista: es un vínculo
    assert campos["Fecha-Principal"] == "2026-09-12"
    assert campos["Atención"] == ["Receta"]
    assert campos["Medicamento 1"] == MEDICAMENTO
    assert campos["Indicacion de medicamento 1"].startswith("Tomar una tableta")
    assert campos["Presentación de medicamento 1"] == PRESENTACION
    assert campos["Date2"] == "2026-10-12"


def test_un_medicamento_que_no_existe_no_se_crea(catalogo):
    r = resolver_receta(lectura(medicamento="Tradea LP 200 mg"), catalogo, HOY)
    campos = construir_campos_receta(r)
    assert "Medicamento 1" not in campos
    assert any("medicamento" in f for f in r.sin_resolver)
    # Pero la nota sí se crea, con el paciente y la fecha.
    assert campos["Paciente"] == ["recJUAN"]


def test_una_presentacion_que_no_existe_no_se_crea(catalogo):
    r = resolver_receta(lectura(presentacion="Caja con 45 tabletas"), catalogo, HOY)
    assert "Presentación de medicamento 1" not in construir_campos_receta(r)
    assert any("presentación" in f for f in r.sin_resolver)


def test_el_catalogo_clinico_caduca():
    viejo = CatalogoClinico(pacientes=(), medicamentos=(), presentaciones=(), momento=0.0)
    assert not viejo.vigente
