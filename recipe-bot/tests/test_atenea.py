"""Atenea: lo que importa es que el bot NO ensucie el catálogo del doctor.

Lugar tiene ~190 opciones y Categoría ~54, ya con duplicados acumulados. Si el
bot pudiera crear opciones nuevas, cada dictado agregaría una variante más.
"""
import pytest

from recipe_bot.atenea import Catalogo, _normalizar
from recipe_bot.models import Movimiento
from recipe_bot.storage.airtable import construir_campos_movimiento, resolver


@pytest.fixture
def catalogo():
    return Catalogo(
        formas_pago={"Inbursa": "recINB", "Amex Platinum": "recAMEX", "Efectivo": "recEFE"},
        lugares=("Walmart", "Office Depot", "Gasolinera", "Súper"),
        categorias=("Súper", "Consultorio LAP", "Comida"),
    )


def movimiento(**kw) -> Movimiento:
    base = dict(
        fecha="2026-09-11", monto=500.0, forma_pago="Inbursa", lugar="Walmart",
        categoria="Súper", detalles=None, confianza="alta", falta=[],
    )
    base.update(kw)
    return Movimiento(**base)


# --- normalización ---------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Súper", "super"), ("WALMART", "Walmart"), ("  Office   Depot ", "office depot"),
])
def test_compara_ignorando_acentos_mayusculas_y_espacios(a, b):
    assert _normalizar(a) == _normalizar(b)


def test_no_confunde_cosas_distintas():
    assert _normalizar("Inbursa") != _normalizar("Invex")


# --- resolución contra el catálogo ----------------------------------------

def test_la_forma_de_pago_se_convierte_en_id_de_registro(catalogo):
    # Forma de pago es un vínculo a Sumandos: Airtable necesita el id, no el texto.
    assert catalogo.resolver_forma_pago("inbursa") == "recINB"
    assert catalogo.resolver_forma_pago("AMEX PLATINUM") == "recAMEX"


def test_una_cuenta_inexistente_no_se_inventa(catalogo):
    assert catalogo.resolver_forma_pago("Banco Azteca") is None


def test_el_lugar_se_empata_aunque_venga_sin_acento(catalogo):
    assert catalogo.resolver_opcion("super", catalogo.lugares) == "Súper"


def test_un_lugar_nuevo_no_se_crea(catalogo):
    assert catalogo.resolver_opcion("Tienda X", catalogo.lugares) is None


# --- campos que se mandan a Airtable ---------------------------------------

def test_movimiento_completo_llena_los_seis_campos(catalogo):
    campos = construir_campos_movimiento(resolver(movimiento(detalles="Despensa"), catalogo))
    assert campos["Fecha"] == "2026-09-11"
    assert campos["Monto"] == 500.0
    assert campos["Forma de pago"] == ["recINB"]   # lista: es un vínculo
    assert campos["Lugar"] == "Walmart"
    assert campos["Categoría"] == "Súper"
    assert campos["Detalles"] == "Despensa"


def test_lo_que_no_esta_en_el_catalogo_se_omite_en_vez_de_crearse(catalogo):
    r = resolver(movimiento(lugar="Tienda X", categoria="Cosas", forma_pago="Banco Azteca"), catalogo)
    campos = construir_campos_movimiento(r)
    assert "Lugar" not in campos
    assert "Categoría" not in campos
    assert "Forma de pago" not in campos
    # Pero el movimiento sí se guarda, con lo que sí se pudo resolver.
    assert campos["Monto"] == 500.0


def test_lo_que_no_empato_queda_escrito_en_detalles(catalogo):
    # Si no, el hueco en la contabilidad sería invisible.
    campos = construir_campos_movimiento(resolver(movimiento(lugar="Tienda X"), catalogo))
    assert "No están en tu catálogo" in campos["Detalles"]
    assert "Tienda X" in campos["Detalles"]


def test_los_detalles_dictados_se_conservan_junto_con_el_aviso(catalogo):
    r = resolver(movimiento(lugar="Tienda X", detalles="Regalo de Sofía"), catalogo)
    campos = construir_campos_movimiento(r)
    assert campos["Detalles"].startswith("Regalo de Sofía")
    assert "Tienda X" in campos["Detalles"]


def test_un_campo_vacio_de_origen_no_cuenta_como_no_resuelto(catalogo):
    # El modelo deja "" cuando lo dictado no menciona el dato; eso no es un error
    # de catálogo, es simplemente que no se dijo.
    r = resolver(movimiento(lugar=""), catalogo)
    assert r.sin_resolver == []
    assert "Lugar" not in construir_campos_movimiento(r)


def test_el_catalogo_caduca_para_que_se_relea(catalogo):
    assert catalogo.vigente
    viejo = Catalogo(formas_pago={}, lugares=(), categorias=(), momento=0.0)
    assert not viejo.vigente
